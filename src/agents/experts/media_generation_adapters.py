from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Optional

import httpx
import requests
from dashscope import ImageSynthesis
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.models import LlmRequest
from google.adk.tools import google_search
from google.genai import types
from google.genai.types import Content, Part
from volcengine.visual.VisualService import VisualService
from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime.types.images.images import SequentialImageGenerationOptions

from src.logger import logger
from src.agents.experts.image_utils import select_aspect_ratio
from src.agents.experts.usage_utils import safe_int


@dataclass
class ImageGenerationResult:
    status: str
    message: bytes | str
    provider: str
    model_name: str
    usage: Optional[dict[str, int]] = None

def _parse_usage_from_obj(obj: Any) -> Optional[dict[str, int]]:
    if obj is None:
        return None

    # common objects that expose usage metadata
    usage = getattr(obj, "usage_metadata", None) or getattr(obj, "usage", None)
    if usage is None and isinstance(obj, dict):
        usage = obj.get("usage_metadata") or obj.get("usage")
    if usage is None:
        return None

    def _get(v: Any, key: str) -> Any:
        if isinstance(v, dict):
            return v.get(key)
        return getattr(v, key, None)

    prompt_tokens = safe_int(_get(usage, "prompt_token_count"))
    completion_tokens = safe_int(_get(usage, "candidates_token_count"))
    total_tokens = safe_int(_get(usage, "total_token_count"))

    # fallback aliases from other providers
    if prompt_tokens <= 0:
        prompt_tokens = safe_int(_get(usage, "input_tokens"))
    if completion_tokens <= 0:
        completion_tokens = safe_int(_get(usage, "output_tokens")) or safe_int(_get(usage, "completion_tokens"))
    if total_tokens <= 0:
        total_tokens = safe_int(_get(usage, "total_tokens")) or (prompt_tokens + completion_tokens)

    if total_tokens <= 0:
        return None
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


async def tongyi_text_to_image(prompt: str, api_key: str) -> ImageGenerationResult:
    try:
        rsp = ImageSynthesis.async_call(
            api_key=api_key,
            model="wanx2.1-t2i-turbo",
            prompt=prompt,
            n=1,
        )
        if rsp.status_code != HTTPStatus.OK:
            return ImageGenerationResult(
                status="error",
                message=f"dashscope task create failed: {rsp.status_code}, {rsp.code}, {rsp.message}",
                provider="dashscope",
                model_name="wanx2.1-t2i-turbo",
            )

        rsp = ImageSynthesis.wait(rsp)
        if rsp.status_code != HTTPStatus.OK:
            return ImageGenerationResult(
                status="error",
                message=f"dashscope task failed: {rsp.status_code}, {rsp.code}, {rsp.message}",
                provider="dashscope",
                model_name="wanx2.1-t2i-turbo",
            )

        if rsp.output.task_status == "FAILED":
            return ImageGenerationResult(
                status="error",
                message=f"dashscope task status failed: {rsp['output']['message']}",
                provider="dashscope",
                model_name="wanx2.1-t2i-turbo",
            )

        for result in rsp.output.results:
            content = requests.get(result.url, timeout=30).content
            return ImageGenerationResult(
                status="success",
                message=content,
                provider="dashscope",
                model_name="wanx2.1-t2i-turbo",
                usage=_parse_usage_from_obj(rsp),
            )

        return ImageGenerationResult(
            status="error",
            message="dashscope returned empty result",
            provider="dashscope",
            model_name="wanx2.1-t2i-turbo",
        )
    except Exception as e:
        return ImageGenerationResult(
            status="error",
            message=f"dashscope exception: {e}",
            provider="dashscope",
            model_name="wanx2.1-t2i-turbo",
        )


async def segmind_gpt_image_1(prompt: str, api_key: str) -> ImageGenerationResult:
    url = "https://api.segmind.com/v1/gpt-image-1"
    timeout = httpx.Timeout(None, connect=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            payload = {
                "prompt": prompt,
                "size": "auto",
                "quality": "auto",
                "moderation": "auto",
                "background": "opaque",
                "output_compression": 100,
                "output_format": "png",
            }
            headers = {"x-api-key": api_key}
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code != HTTPStatus.OK:
            return ImageGenerationResult(
                status="error",
                message=f"segmind error {response.status_code}: {response.content[:500]}",
                provider="segmind",
                model_name="gpt-image-1",
            )
        return ImageGenerationResult(
            status="success",
            message=response.content,
            provider="segmind",
            model_name="gpt-image-1",
        )
    except Exception as e:
        return ImageGenerationResult(
            status="error",
            message=f"segmind exception: {e}",
            provider="segmind",
            model_name="gpt-image-1",
        )


async def gemini_image_generation(
    ctx: InvocationContext,
    prompt: str,
    *,
    aspect_ratio: str = "16:9",
    resolution: str = "1K",
) -> ImageGenerationResult:
    aspect_ratio = select_aspect_ratio(aspect_ratio)
    try:
        def before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
            llm_request.contents.append(
                Content(role="user", parts=[Part(text=prompt)])
            )

        llm = LlmAgent(
            name="media_gemini_image_generation",
            model="gemini-3.1-flash-image-preview",
            instruction="Generate an image according to the prompt.",
            include_contents="none",
            tools=[google_search],
            generate_content_config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=resolution,
                ),
            ),
            before_model_callback=before_model_callback,
        )

        text_message = ""
        image_data: Optional[bytes] = None
        usage = None
        async for event in llm.run_async(ctx):
            parsed_usage = _parse_usage_from_obj(event)
            if parsed_usage:
                usage = parsed_usage
            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                if part.text is not None:
                    text_message = part.text
                elif part.inline_data is not None:
                    image_data = part.inline_data.data

        if image_data:
            return ImageGenerationResult(
                status="success",
                message=image_data,
                provider="gemini",
                model_name="gemini-3.1-flash-image-preview",
                usage=usage,
            )
        return ImageGenerationResult(
            status="error",
            message=text_message or "gemini returned no image",
            provider="gemini",
            model_name="gemini-3.1-flash-image-preview",
        )
    except Exception as e:
        return ImageGenerationResult(
            status="error",
            message=f"gemini exception: {e}",
            provider="gemini",
            model_name="gemini-3.1-flash-image-preview",
        )


async def jimeng_image_generation(prompt: str) -> ImageGenerationResult:
    try:
        visual_service = VisualService()
        visual_service.set_ak(os.environ.get("JIMENG_AK"))
        visual_service.set_sk(os.environ.get("JIMENG_SK"))

        form = {
            "req_key": "jimeng_t2i_v40",
            "prompt": prompt,
            "scale": 0.5,
        }
        resp = visual_service.cv_process(form)
        if resp.get("message") != "Success":
            return ImageGenerationResult(
                status="error",
                message=f"jimeng error: {resp.get('message')}",
                provider="jimeng",
                model_name="jimeng_t2i_v40",
            )

        image_base64 = resp.get("data", {}).get("binary_data_base64")
        if not isinstance(image_base64, list) or not image_base64:
            return ImageGenerationResult(
                status="error",
                message="jimeng returned invalid binary_data_base64",
                provider="jimeng",
                model_name="jimeng_t2i_v40",
            )
        img_data = base64.b64decode(image_base64[0])
        return ImageGenerationResult(
            status="success",
            message=img_data,
            provider="jimeng",
            model_name="jimeng_t2i_v40",
            usage=_parse_usage_from_obj(resp),
        )
    except Exception as e:
        return ImageGenerationResult(
            status="error",
            message=f"jimeng exception: {e}",
            provider="jimeng",
            model_name="jimeng_t2i_v40",
        )


async def seedream_image_generation(prompt: str, ark_api_key: str) -> ImageGenerationResult:
    try:
        client = Ark(
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=ark_api_key,
        )
        response = client.images.generate(
            model="doubao-seedream-4-0-250828",
            prompt=prompt,
            size="2K",
            sequential_image_generation="auto",
            sequential_image_generation_options=SequentialImageGenerationOptions(max_images=10),
            response_format="b64_json",
            watermark=False,
        )
        if response.error:
            return ImageGenerationResult(
                status="error",
                message="seedream generation failed",
                provider="seedream",
                model_name="doubao-seedream-4-0-250828",
            )

        for item in response.data:
            img_data = base64.b64decode(item.b64_json)
            return ImageGenerationResult(
                status="success",
                message=img_data,
                provider="seedream",
                model_name="doubao-seedream-4-0-250828",
                usage=_parse_usage_from_obj(response),
            )

        return ImageGenerationResult(
            status="error",
            message="seedream returned empty images",
            provider="seedream",
            model_name="doubao-seedream-4-0-250828",
        )
    except Exception as e:
        logger.error(f"seedream exception: {e}", exc_info=True)
        return ImageGenerationResult(
            status="error",
            message=f"seedream exception: {e}",
            provider="seedream",
            model_name="doubao-seedream-4-0-250828",
        )
