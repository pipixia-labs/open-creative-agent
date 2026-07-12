import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException

from conf.system import SYS_CONFIG
from server.agents_manager import session_service
from server.services.conversation_service import conversation_service
from server.utils.session_auth import get_current_user_id
from server.utils.util import SessionCreateResponse
from src.context import username_context
from src.logger import logger
from src.utils import database_op_with_retry


router = APIRouter()


@router.post("/session/create", response_model=SessionCreateResponse)
async def create_session_endpoint(
    user_id: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
    current_user_id: str = Depends(get_current_user_id),
):
    """Create a local ADK session and matching conversation metadata."""
    logger.debug(
        f"[/session/create] Request received | user_id={user_id}, "
        f"auth_user_id={current_user_id}, username={username}"
    )
    username_context.set(username or "anonymous")
    if user_id and user_id != current_user_id:
        logger.warning(
            f"[/session/create] Ignoring mismatched user_id form value. "
            f"claimed={user_id}, actual={current_user_id}"
        )

    uid = current_user_id
    session_id_val = f"{SYS_CONFIG.session_id_default_prefix}{uuid.uuid4()}"
    try:
        await database_op_with_retry(
            session_service.create_session,
            app_name=SYS_CONFIG.app_name,
            user_id=uid,
            state={},
            session_id=session_id_val,
            logger=logger,
            op_name="create_session_endpoint",
        )

        await conversation_service.create_session(
            session_id=session_id_val,
            user_id=uid,
        )

        logger.info(f"Session created successfully | user={username}, session_id={session_id_val}, user_id={uid}")

        return SessionCreateResponse(
            user_id=uid,
            session_id=session_id_val,
            message="Session created successfully.",
        )

    except Exception as e:
        logger.error(f"Failed to create session | user_id={uid}, error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")
