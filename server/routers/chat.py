from typing import Any, List, Optional
from pathlib import Path
import asyncio
import json
import mimetypes

from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from server.agents_manager import session_service, artifact_service, expert_runners, expert_agents
from server.utils.common import set_initial_state
from server.services.conversation_service import conversation_service
from server.services.task_manager import task_manager
from src.agents.orchestrator.orchestrator_agent import Orchestrator
from src.agents.executor.executor_agent import Executor
from conf.system import SYS_CONFIG
from src.logger import logger
from src.context import username_context
from server.utils.util import save_upload_file_sync, format_sse_event, current_time_str, encode_media
from server.utils.session_auth import get_current_user_id
from src.utils import database_op_with_retry

router = APIRouter()

outputs_dir_name = "outputs"
outputs_path = Path(SYS_CONFIG.base_dir) / outputs_dir_name
outputs_path.mkdir(parents=True, exist_ok=True)

images_dir_name = "images"
images_dir = outputs_path / images_dir_name
images_dir.mkdir(parents=True, exist_ok=True)

videos_dir_name = "videos"
videos_dir = outputs_path / videos_dir_name
videos_dir.mkdir(parents=True, exist_ok=True)

uploads_dir_name = "uploads"
uploads_dir = outputs_path / uploads_dir_name
uploads_dir.mkdir(parents=True, exist_ok=True)

router.mount(f"/{outputs_dir_name}", StaticFiles(directory=outputs_path), name="outputs")
logger.info(f"Static files are served at: /{outputs_dir_name}, corresponding directory: {outputs_path}")

DOC_EXT_TO_MIME = {
    ".pdf": {
        "application/pdf",
    },
    ".doc": {
        "application/msword",
    },
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },

    ".ppt": {
        "application/vnd.ms-powerpoint",
    },
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    },

    ".xls": {
        "application/vnd.ms-excel",
    },
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },

    ".csv": {
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
    },
    ".txt": {
        "text/plain",
    },
    ".md": {
        "text/markdown",
        "text/plain",
    },
    ".zip": {
        "application/zip",
        "application/x-zip-compressed",
    },
}

ALLOWED_DOC_EXT = set(DOC_EXT_TO_MIME.keys())

ALLOWED_DOC_MIME = {
    mime
    for mimes in DOC_EXT_TO_MIME.values()
    for mime in mimes
}

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp"}


def _ext(name: str) -> str:
    name = (name or "").lower()
    return name[name.rfind("."):] if "." in name else ""


def _collect_doc_filenames(artifacts_history: list[Any]) -> list[str]:
    """Collect document filenames from all artifact steps, preserving first-seen order."""
    filenames: list[str] = []
    seen: set[str] = set()
    for artifact_group in artifacts_history:
        if not isinstance(artifact_group, list):
            continue
        for art in artifact_group:
            if not isinstance(art, dict):
                continue
            name = str(art.get("name") or "").strip()
            if not name or "search" in name or name in seen:
                continue
            if _ext(name) in ALLOWED_DOC_EXT:
                filenames.append(name)
                seen.add(name)
    return filenames


def _find_artifact_path_in_state(state: dict[str, Any], filename: str) -> Optional[str]:
    """Find a saved artifact path in session state by filename."""
    target_name = str(filename or "").strip()
    if not target_name:
        return None

    candidate_groups: list[Any] = []
    candidate_groups.extend(state.get("artifacts_history") or [])
    candidate_groups.append(state.get("new_artifacts") or [])
    candidate_groups.append(state.get("input_artifacts") or [])

    for group in candidate_groups:
        if not isinstance(group, list):
            continue
        for art in group:
            if not isinstance(art, dict):
                continue
            name = str(art.get("name") or "").strip()
            path = art.get("path")
            if name == target_name and isinstance(path, str) and path.strip():
                return path
    return None


def _build_final_data(final_session: Any, final_summary: str) -> dict[str, Any]:
    """Build final payload for SSE/frontend from final session state."""
    artifacts_history = final_session.state.get("artifacts_history")
    final_steps = len(artifacts_history)
    final_art = []
    for i in range(final_steps):
        if len(artifacts_history[final_steps - 1 - i]) > 0:
            for art in artifacts_history[final_steps - 1 - i]:
                ext_name = _ext(art["name"])
                if "search" not in art["name"] and ext_name not in ALLOWED_DOC_EXT:
                    final_art.append(art)

    final_filenames = _collect_doc_filenames(artifacts_history)
    for filename in final_filenames:
        logger.info(f"final doc artifact: {filename}, ext: {_ext(filename)}")

    final_art_base64 = [encode_media(art["path"]) for art in final_art]
    final_art_base64 = [f for f in final_art_base64 if f is not None]

    final_output_text = ""
    text_history = final_session.state.get("text_history", [])
    if len(text_history) > 0 and text_history[-1]:
        final_output_text = text_history[-1]

    final_output_text = (
        final_output_text + f"\nThe current task has been completed, number of steps: {final_steps}\n"
    )
    logger.info(f"final_output_text: {final_output_text}")

    return {
        "text": final_summary,
        "final_output_text": str(final_output_text) if final_output_text else None,
        "image": final_art_base64,
        "filenames": final_filenames,
        "_meta": {
            "step_count": final_steps,
            "artifact_count": len(final_art) + len(final_filenames),
            "artifacts": [{"name": art["name"], "path": art.get("path")} for art in final_art],
        },
    }


@router.post("/chat")
async def chat_with_agent(
    message: str = Form(...),
    session_id: str = Form(...),
    user_id: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
    images: Optional[List[UploadFile]] = File(None),
    documents: Optional[List[UploadFile]] = File(None),
    current_user_id: str = Depends(get_current_user_id),
):
    username_context.set(username or "anonymous")

    logger.info(f"user_id: {user_id}, username: {username}, images: {images}, documents: {documents}")
    images = images or []

    img_paths = []
    for image in images:
        if image and image.filename:
            ext = _ext(image.filename)
            if ext not in ALLOWED_IMAGE_EXT:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported image file type: {image.filename} ({ext})"
                )
            img_path = save_upload_file_sync(image, uploads_dir)
            if len(img_path) > 0:
                img_paths.append(img_path)
                logger.info(f"Received image: {image.filename} ({image.content_type})")
        else:
            img_paths.append(None)

    document_paths = []
    if documents:
        for document in documents:
            if not document or not document.filename:
                continue

            content_type = (document.content_type or "").lower()
            ext = _ext(document.filename)

            if content_type not in ALLOWED_DOC_MIME and ext not in ALLOWED_DOC_EXT:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type: {document.filename} ({document.content_type})"
                )

            document_path = save_upload_file_sync(document, uploads_dir)
            if len(document_path) > 0:
                document_paths.append(document_path)
                logger.info(f"Received document: {document.filename} ({document.content_type})")

    uid = user_id or current_user_id
    sid = session_id

    if await task_manager.is_running(sid):
        raise HTTPException(
            status_code=409,
            detail={"error": "session_task_running", "message": "A task is already running for this session."},
        )

    debug_username_set = set(SYS_CONFIG.DEBUG_USERS)
    event_queue: asyncio.Queue = asyncio.Queue(maxsize=512)

    async def emit(
        *,
        msg_type: str,
        event_type: str,
        content: Any,
        artifacts: Optional[List[dict[str, Any]]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        await conversation_service.append_message(
            session_id=sid,
            user_id=uid,
            msg_type=msg_type,
            content=content if isinstance(content, str) else json.dumps(content, ensure_ascii=False),
            artifacts=artifacts,
            metadata=metadata,
        )
        try:
            event_queue.put_nowait({"type": event_type, "content": content})
        except asyncio.QueueFull:
            logger.warning(f"Event queue full, dropping event | sid={sid}, event_type={event_type}")

    async def run_workflow() -> None:
        logger.info(f"Workflow started | uid={uid}, username={username}, sid={sid}, user_instruction={message}")
        await conversation_service.update_session_status(sid, status="running")
        try:
            await conversation_service.append_message(
                session_id=sid,
                user_id=uid,
                msg_type="user_input",
                content=message,
                artifacts=[{"type": "image", "path": p} for p in img_paths if p],
                metadata={"documents": document_paths} if document_paths else None,
            )

            step_content = f"User instruction: {message}"
            if username in debug_username_set:
                step_content = f"{current_time_str()}  {step_content}"
            await emit(msg_type="step", event_type="step", content=step_content)

            for index, img_path in enumerate(img_paths, start=1):
                if img_path:
                    step_content = f"Image {index} received: {Path(img_path).name}"
                    await emit(msg_type="step", event_type="step", content=step_content)

            current_session = await database_op_with_retry(
                session_service.get_session,
                app_name=SYS_CONFIG.app_name,
                user_id=uid,
                session_id=sid,
            )
            if not current_session:
                raise ValueError(f"Session {sid} (User {uid}) not found.")

            await set_initial_state(uid, sid, message, img_paths, document_paths)

            orchestrator = Orchestrator(
                session_service=session_service,
                artifact_service=artifact_service,
                app_name=SYS_CONFIG.app_name,
                llm_model_plan=SYS_CONFIG.orchestrator_llm_model,
                llm_model_critic=SYS_CONFIG.critic_llm_model,
                max_iter=SYS_CONFIG.plan_critic_iter_num,
                internal=True,
            )
            executor = Executor(
                session_service=session_service,
                artifact_service=artifact_service,
                app_name=SYS_CONFIG.app_name,
                expert_runners=expert_runners,
                llm_model=SYS_CONFIG.executor_llm_model,
                executor_replan_enabled=SYS_CONFIG.executor_replan_enabled,
            )

            orchestrator.uid = uid
            orchestrator.sid = sid
            orchestrator.username = username
            executor.uid = uid
            executor.sid = sid
            executor.username = username
            executor.save_dir = images_dir

            global_plan, global_summary = await orchestrator.generate_plan(global_plan=True)
            logger.info(f"Global step planning:\n {global_summary}")
            if username in debug_username_set:
                step_content = f"{current_time_str()}  Orchestrator global plan: {global_plan}"
                await emit(
                    msg_type="step",
                    event_type="step",
                    content=step_content,
                    metadata={"global_plan": global_plan},
                )
                step_content = f"{current_time_str()}  Orchestrator: {global_summary}"
                await emit(msg_type="step", event_type="step", content=step_content)
            else:
                step_content = f"Orchestrator: {global_summary}"
                await emit(
                    msg_type="step",
                    event_type="step",
                    content=step_content,
                    metadata={"global_plan": global_plan},
                )

            final_summary = "The task process has been initiated."
            max_loops = SYS_CONFIG.max_iterations_orchestrator
            for i in range(max_loops):
                logger.info(f"--- Workflow loop: Round {i + 1}/{max_loops} (Session: {sid}) ---")

                current_session = await database_op_with_retry(
                    session_service.get_session,
                    app_name=SYS_CONFIG.app_name,
                    user_id=uid,
                    session_id=sid,
                )
                logger.debug(
                    f"State snapshot (Orchestrator input): {json.dumps(current_session.state, indent=2, ensure_ascii=False)}"
                )

                plan, current_summary = await orchestrator.generate_plan(global_plan=False)
                next_agent_name = plan.get("next_agent")
                params_for_expert = plan.get("parameters", {})
                final_summary = current_summary

                if username in debug_username_set:
                    step_content = f"{current_time_str()}  Orchestrator next action: {plan}"
                    await emit(
                        msg_type="step",
                        event_type="step",
                        content=step_content,
                        metadata={"plan": plan, "loop": i},
                    )

                if not next_agent_name or next_agent_name == "FINISH":
                    logger.info(f"Orchestrator finished the task. Summary: {final_summary}")
                    break

                if next_agent_name not in expert_agents:
                    logger.error(f"Orchestrator selected unknown agent: '{next_agent_name}'. End loop.")
                    final_summary = f"Orchestrator selected unknown agent '{next_agent_name}', task ends."
                    break

                if i == 0:
                    if username in debug_username_set:
                        step_content = f"{current_time_str()}  Plan has been formulated, and expert agents are executing..."
                    else:
                        step_content = "Plan has been formulated, and expert agents are executing..."
                    await emit(msg_type="step", event_type="step", content=step_content)

                if username in debug_username_set:
                    step_content = (
                        f"{current_time_str()}  Delegating task to expert: {next_agent_name}. \n Parameter: {params_for_expert}\n"
                    )
                    await emit(
                        msg_type="step",
                        event_type="step",
                        content=step_content,
                        metadata={"expert": next_agent_name, "parameters": params_for_expert},
                    )

                current_output = await executor.execute_plan()
                current_artifacts = current_output.get("output_artifacts", [])

                if username in debug_username_set:
                    text = current_output["message"]
                    if "output_text" in current_output:
                        text += f"\n{current_output['output_text']}"
                    step_content = f"{current_time_str()}  Execution result: agent {i} {text}"
                else:
                    message_for_user = current_output.get("message_for_user") or current_output["message"]
                    step_content = f"--> Execution result: agent {i} {message_for_user}"

                await emit(
                    msg_type="step",
                    event_type="step",
                    content=step_content,
                    artifacts=current_artifacts,
                    metadata={"expert": next_agent_name, "loop": i},
                )
            else:
                logger.warning(f"Workflow reached the maximum number of loops {max_loops}, forcing termination.")
                final_summary = (
                    f"The task reached the maximum step limit ({max_loops}) and has been automatically terminated."
                )

            final_session = await database_op_with_retry(
                session_service.get_session,
                app_name=SYS_CONFIG.app_name,
                user_id=uid,
                session_id=sid,
            )
            final_data = _build_final_data(final_session, final_summary)
            final_meta = final_data.pop("_meta")

            await conversation_service.append_message(
                session_id=sid,
                user_id=uid,
                msg_type="final",
                content=final_summary,
                artifacts=final_meta["artifacts"],
                metadata={
                    "filenames": final_data.get("filenames", []),
                    "output_text": final_data.get("final_output_text"),
                    "step_count": final_meta["step_count"],
                },
            )

            await conversation_service.update_session_status(
                sid,
                status="completed",
                step_count=final_meta["step_count"],
                artifact_count=final_meta["artifact_count"],
            )

            try:
                event_queue.put_nowait({"type": "final", "content": final_data})
            except asyncio.QueueFull:
                logger.warning(f"Event queue full, dropping final event | sid={sid}")
        except Exception as e:
            error_text = f"Task execution failed: {str(e)}"
            logger.error(error_text, exc_info=True)
            await conversation_service.append_message(
                session_id=sid, user_id=uid, msg_type="error", content=error_text
            )
            await conversation_service.update_session_status(sid, status="error", error_message=str(e))
            try:
                event_queue.put_nowait({"type": "error", "content": error_text})
            except asyncio.QueueFull:
                logger.warning(f"Event queue full, dropping error event | sid={sid}")

    workflow_task = asyncio.create_task(run_workflow())
    await task_manager.register(session_id=sid, user_id=uid, task=workflow_task, queue=event_queue)

    async def event_stream():
        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                yield format_sse_event(event)
                if event.get("type") in {"final", "error"}:
                    break
            except TimeoutError:
                if workflow_task.done():
                    break
            except asyncio.CancelledError:
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/file/download")
async def download_file(
                session_id: str,
                filename: str,
                user_id: Optional[str] = Query(None),
                current_user_id: str = Depends(get_current_user_id),
):
    """Download a generated artifact file from local session storage."""
    if user_id and user_id != current_user_id:
        logger.warning(
            f"[/file/download] Ignore mismatched user_id query value. claimed={user_id}, actual={current_user_id}"
        )

    user_id = current_user_id
    try:
        current_session = await database_op_with_retry(
            session_service.get_session,
            app_name=SYS_CONFIG.app_name,
            user_id=user_id,
            session_id=session_id,
            logger=logger,
            op_name="download_file_get_session",
        )
        session_state = getattr(current_session, "state", {}) if current_session else {}
        file_path = _find_artifact_path_in_state(session_state, filename)
        if file_path:
            path_obj = Path(file_path)
            if path_obj.exists() and path_obj.is_file():
                mime_type, _ = mimetypes.guess_type(filename)
                return StreamingResponse(
                    path_obj.open("rb"),
                    media_type=mime_type or "application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename={filename}"},
                )

        artifact_part = await artifact_service.load_artifact(
            app_name=SYS_CONFIG.app_name,
            user_id=user_id,
            session_id=session_id,
            filename=filename,
        )
        if not artifact_part:
            raise HTTPException(status_code=404, detail="Artifact not found.")

        file_data = artifact_part.inline_data.data
        mime_type = artifact_part.inline_data.mime_type or "application/octet-stream"

        return StreamingResponse(
            iter([file_data]),
            media_type=mime_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file {filename} for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")
