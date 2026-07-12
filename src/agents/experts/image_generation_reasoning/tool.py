
import requests
import httpx
from typing import Any, Dict, AsyncGenerator
from http import HTTPStatus
from PIL import Image
from io import BytesIO
import base64
import os
import urllib3


from dashscope import ImageSynthesis
from google.adk.tools import ToolContext
from google.adk.tools import google_search
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest
from src.llm.model_factory import build_model_and_config
from google.genai.types import Part, Content

from google.genai import types

from volcengine.visual.VisualService import VisualService
from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime.types.images.images import SequentialImageGenerationOptions

from conf.system import SYS_CONFIG
from conf.api import API_CONFIG
from src.logger import logger
from src.agents.experts.image_utils import select_aspect_ratio
from src.agents.experts.usage_utils import parse_usage_obj


async def nano_banana_image_generation_tool(
    ctx: InvocationContext,
    prompt: str,
    aspect_ratio="16:9",
    resolution="1K",
) -> AsyncGenerator[dict[str, Any], None]:
    # aspect_ratio = "16:9"  # "1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9"
    # resolution = "2K"  # "1K", "2K", "4K"
    logger.info("calling nano banana for reasoning image generation ...")
    aspect_ratio = select_aspect_ratio(aspect_ratio)

    try:
        def before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
            llm_request.contents.append(Content(role="user", parts=[Part(text=prompt)]))

        llm = LlmAgent(
            name="reasoning_image_generation_nano_banana",
            model="gemini-3.1-flash-image-preview",
            instruction="Generate images according to the user prompt.",
            include_contents="none",
            tools=[google_search],
            generate_content_config=types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE'],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=resolution
                )
            ),
            before_model_callback=before_model_callback,
        )

        text_message = []
        img_message = []

        usage = None
        async for event in llm.run_async(ctx):
            parsed_usage = parse_usage_obj(event)
            if parsed_usage:
                usage = parsed_usage
            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                if part.text is not None:
                    text_message.append(part.text)
                elif part.inline_data is not None:
                    img_message.append(part.inline_data.data)

        if img_message is not None  and len(img_message) > 0:
            result = {
                'status': "success",
                "images": img_message,
                'message': text_message,
                "provider": "gemini",
                "model_name": "gemini-3.1-flash-image-preview",
                "usage": usage,
            }
            logger.info(f"nano_banana image generation completed. image_count={len(img_message)}")
        else:
            result = {
                'status': "error",
                "message": text_message,
                "provider": "gemini",
                "model_name": "gemini-3.1-flash-image-preview",
                "usage": usage,
            }

        return result

    except Exception as e:
        error_msg = f"[nano_banana_image_generation_tool] 发生异常: {e}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "error",
            "message": error_msg,
            "provider": "gemini",
            "model_name": "gemini-3.1-flash-image-preview",
            "usage": None,
        }
