from typing import Any, Dict, AsyncGenerator
import os
from google.adk.tools import ToolContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest
from src.llm.model_factory import build_model_and_config
from google.genai.types import Part, Content

from conf.system import SYS_CONFIG
from conf.api import API_CONFIG
from src.logger import logger
from src.agents.experts.media_generation_adapters import (
    tongyi_text_to_image,
    segmind_gpt_image_1,
    gemini_image_generation,
    jimeng_image_generation,
    seedream_image_generation,
)
from server.services.token_usage_service import token_usage_service


async def prompt_enhancement_tool(ctx: InvocationContext, prompt: str) -> AsyncGenerator[str, None]:
    system_prompt = """
    你是一个专业的提示词优化专家，精通文生图领域的提示词具体化和优化工作。
    用户会输入初始的图像生成prompt，你需要根据prompt进行润色或扩写。
    你的任务分为两种情况：
    1. 用户输入了模糊简短的指令（通常为一个简短的不包含任何细节的句子）
    此时你需要根据这些模糊的指令，生成一个更详细、更具创意和高质量的提示词。图像的具体内容细节全都由你来决定，但是需要保持与原始输入指令一致。

    2. 用户输入较为详细的指令（通常为超过100词的长句）
    此时你不需要添加任何画面内容，而是需要对prompt进行润色，你的润色主要集中在以下几个方面：
    **画面细节**：可以对原始prompt中的细节进行强调
    **特殊元素**：如果原始prompt中存在文字，标志等元素，你需要使其描述更加精确。
    注意！这种情况下你必须保证新生成的prompt与原始prompt严格一致，不能损失或改变任何语义内容，只能润色或强调。

    # 以下是一些prompt优化的示例：
    <ori>用户输入：一只帅气的猫坐在沙滩椅上，背后是沙滩。</ori>
    <opt>优化后的提示词：一只可爱有点痞气的大胖猫，在躺椅上戴着墨镜，带着铭牌项圈，手拿红酒杯躺着沙滩上晒太阳，身下垫着浴巾，猫朝向大海。</opt>
    <ori>一个男生正在挥动拍子击打羽毛球。</ori>
    <opt>优化后的提示词：一个身材高大的男生，穿着运动服，正专注地挥动羽毛球拍，准备击打空中飞来的羽毛球，背景是一个明亮的室内羽毛球场。咒语/关键词：羽毛球运动,水墨画,水彩,氛围光照,伦勃朗光,俯视视角,水墨人像</opt>

    # 注意：
    - 你只需要输出优化后的提示词文本，不要输出md或json对象。
    - 不要指定输出文件的名字，系统会自动命名生成的图像文件。
    - 如果输入的prompt中有尺寸的表达不符合常见模型的要求（比如`#9865` , `1024x768`, `1080x1990px`），你需要将其删除，防止模型认为那是需要生成的文字内容。
    """

    def before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
        design_suggestions = callback_context.state.get('design_suggestions', '')
        if design_suggestions and len(design_suggestions) > 0:
            design_suggestions = design_suggestions + f"当前设计专家智能体 ArtKnowledgeAgent 给的设计建议是：{design_suggestions} \n\n"
            design_suggestions = design_suggestions + """
注意：这些建议中可能会有多种需要探索的方案，但是你现在需要优化的是其中的一种，
需要优化的prompt将会在下面描述。你需要关注你需要优化的哪一种，然后参考相建议中对应的细节信息进行优化。不要混淆其他方案中的细节。
优化后的prompt里面只含有prompt，不要添加其他的无关的信息，比如 'reference information' 等。因为优化后的prompt会被直接送给文生图模型来生成图像，有额外信息会导致图像生成不符合预期。
            \n\n"""

            user_prompt = design_suggestions +  f"这是你当前需要优化的 prompt：\n{prompt}。\n请参考ArtKnowledgeAgent 给的设计建议，对其进行润色或扩写。\n\n"
        else:
            user_prompt = f"这是用户输入的原始 prompt：\n{prompt}。\n请对其进行润色或扩写。"

        llm_request.contents.append(Content(role='user', parts=[Part(text=user_prompt)]))

    llm_model = SYS_CONFIG.llm_model
    llm_model, llm_config = build_model_and_config(llm_model)

    llm = LlmAgent(
        name="prompt_enhancement",
        model=llm_model,
        generate_content_config=llm_config,
        instruction=system_prompt,
        include_contents='none',
        before_model_callback=before_model_callback
    )
    
    try:
        enhanced_prompt = None
        async for event in llm.run_async(ctx):
            await token_usage_service.record_event_usage(
                user_id=ctx.session.user_id,
                session_id=ctx.session.id,
                event=event,
                component="expert_tool",
                agent_name="ImageGenerationPromptEnhancementTool",
            )
            if event.is_final_response() and event.content and event.content.parts:
                generated_text = next((part.text for part in event.content.parts if part.text), None)
                if generated_text:
                    enhanced_prompt = generated_text
        if enhanced_prompt:
            return {
                'status': 'success',
                'message': enhanced_prompt
            }
        else:
            return {
                'status': 'error',
            'message': "LlmAgent call failed"
            }
            

    except Exception as e:
        error_text = f"LlmAgent failed: {str(e)}"
        logger.error(error_text)
        return {
            'status': 'error',
            'message': error_text
        }

async def tongyi_text2image_tool(prompt: str) -> AsyncGenerator[dict[str, Any], None]:
    """Generate an image from text with the Tongyi Wanxiang image API."""

    logger.info(f"[text2image_tool] called with prompt='{prompt}'")
    dashscope_api_key = API_CONFIG.DASHSCOPE_API_KEY
    if not dashscope_api_key:
        return {
            "status": "error",
            "message": "DASHSCOPE_API_KEY was not found in the environment.",
        }
    result = await tongyi_text_to_image(prompt, dashscope_api_key)
    return {
        "status": result.status,
        "message": result.message,
        "provider": result.provider,
        "model_name": result.model_name,
        "usage": result.usage,
    }



async def GPTimage1_text2image_tool(prompt: str) -> AsyncGenerator[dict[str, Any], None]:
    logger.info("calling segmind GPT-image-1 API for image generation  ...")
    result = await segmind_gpt_image_1(prompt, API_CONFIG.SEGMIND_API_KEY)
    return {
        "status": result.status,
        "message": result.message,
        "provider": result.provider,
        "model_name": result.model_name,
        "usage": result.usage,
    }

async def nano_banana_image_generation_tool(
    ctx: InvocationContext,
    prompt: str,
    aspect_ratio="16:9",
    resolution="1K",
) -> AsyncGenerator[dict[str, Any], None]:
    # aspect_ratio = "16:9"  # "1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9"
    # resolution = "2K"  # "1K", "2K", "4K"
    logger.info("calling nano banana for image generation ...")

    result = await gemini_image_generation(
        ctx,
        prompt,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
    )
    if result.status == "success" and isinstance(result.message, (bytes, bytearray)):
        logger.info(f"nano_banana image generation completed. bytes={len(result.message)}")
    return {
        "status": result.status,
        "message": result.message,
        "provider": result.provider,
        "model_name": result.model_name,
        "usage": result.usage,
    }


async def jimeng_image_generation_tool(prompt: str) -> AsyncGenerator[dict[str, Any], None]:
    logger.info("calling jimeng for image generation ...")
    result = await jimeng_image_generation(prompt)
    if result.status == "success" and isinstance(result.message, (bytes, bytearray)):
        logger.info(f"jimeng image generation completed. bytes={len(result.message)}")
    return {
        "status": result.status,
        "message": result.message,
        "provider": result.provider,
        "model_name": result.model_name,
        "usage": result.usage,
    }



async def seedream_image_generation_tool(prompt: str) -> AsyncGenerator[dict[str, Any], None]:
    logger.info("calling seedream for image generation ...")
    ark_api_key = os.environ.get("ARK_API_KEY") or ""
    result = await seedream_image_generation(prompt, ark_api_key)
    return {
        "status": result.status,
        "message": result.message,
        "provider": result.provider,
        "model_name": result.model_name,
        "usage": result.usage,
    }
