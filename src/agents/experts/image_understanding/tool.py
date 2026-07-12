from typing import Dict, Any

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.models import LlmRequest
from google.adk.models.lite_llm import LiteLlm
from src.llm.model_factory import build_model_and_config
from google.genai.types import Content, Part

from conf.api import API_CONFIG
from conf.system import SYS_CONFIG
from src.logger import logger
from src.agents.experts.image_utils import get_image_info_from_bytes
from server.services.token_usage_service import token_usage_service

async def image_to_text_tool(ctx: InvocationContext, input_name: str, mode: str = 'description') -> Dict[str, Any]:
    """Analyze one image with the configured vision model and return text output."""
    tool_name_for_log = "image_to_text_tool"
    
    # artifact_part = await tool_context.load_artifact(filename=input_name)
    artifact_part = await ctx.artifact_service.load_artifact(filename=input_name,
                                                             app_name=ctx.session.app_name,
                                                             user_id=ctx.session.user_id,
                                                             session_id=ctx.session.id)
    if not artifact_part:
        return {"status": "error", "message": f"artifact not found: {input_name}"}

    basic_info = get_image_info_from_bytes(artifact_part.inline_data.data)

    # API-KEY
    DASHSCOPE_API_KEY = API_CONFIG.DASHSCOPE_API_KEY

    # prompt
    prompts_map = {
        "description": "请详细描述这张图片的内容，包括主要的物体、场景、氛围以及可能的故事情节。",
        "style": "请分析并描述这张图片的艺术风格，例如绘画流派、色彩运用、构图特点、光影效果以及整体给人的感觉。",
        "ocr": "请提取这张图片中的所有文字内容。如果包含多种语言，请分别列出。",
        "all": "请详细描述这张图片的内容，包括主要的物体、场景、氛围以及可能的故事情节。然后分析并描述这张图片的艺术风格，例如绘画流派、色彩运用、构图特点、光影效果以及整体给人的感觉。最后请提取这张图片中的所有文字内容。如果包含多种语言，请分别列出。",
    }
    text_prompt = prompts_map.get(mode, prompts_map['description'])

    def before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
        llm_request.contents.append(
            Content(
                role="user",
                parts=[Part(text=text_prompt), artifact_part],
            )
        )

    # Keep the original model/provider path while switching to ADK LLM invocation.
    llm_model = LiteLlm(
        model="openai/qwen-vl-plus-latest",
        # model="openai/qwen3-vl-flash",
        api_key=DASHSCOPE_API_KEY,
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    llm_config = None

    # Fallback to system model when dashscope config is unavailable.
    if not DASHSCOPE_API_KEY:
        raw_model = SYS_CONFIG.llm_model
        llm_model, llm_config = build_model_and_config(raw_model)

    llm = LlmAgent(
        name="ImageUnderstandingToolAgent",
        model=llm_model,
        generate_content_config=llm_config,
        instruction="你是一个专业的图片分析师。请严格根据用户需求分析图像并输出清晰结论。",
        include_contents="none",
        before_model_callback=before_model_callback,
    )

    # call via ADK LlmAgent
    try:
        logger.info(f"[{tool_name_for_log}] called: name='{input_name}', mode='{mode}'")
        output_text = ""
        async for event in llm.run_async(ctx):
            await token_usage_service.record_event_usage(
                user_id=ctx.session.user_id,
                session_id=ctx.session.id,
                event=event,
                component="expert_tool",
                agent_name="ImageUnderstandingTool",
            )
            if event.is_final_response() and event.content and event.content.parts:
                generated_text = next((part.text for part in event.content.parts if part.text), None)
                if generated_text:
                    output_text = generated_text

        if not output_text:
            return {"status": "error", "message": "LlmAgent did not return response text"}

        logger.info(f"[{tool_name_for_log}] image analysis success")
        output_text = output_text + '这个图像的基本信息为：' + basic_info + '\n'
        return {'status': 'success', 'message': output_text}

    except Exception as e:
        logger.exception("[{}] image analysis failed: {}", tool_name_for_log, e)
        return {"status": "error", "message": f"image analysis failed: {e}"}
