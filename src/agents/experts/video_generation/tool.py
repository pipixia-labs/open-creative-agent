
import requests
import httpx
from typing import Any, Dict, AsyncGenerator
from http import HTTPStatus
from PIL import Image
from io import BytesIO
import base64
import urllib3
import os
import time
import urllib.request
import mimetypes

from dashscope import ImageSynthesis
from google.adk.tools import ToolContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest
from src.llm.model_factory import build_model_and_config
from google.genai.types import Part, Content

from google import genai
from google.genai import types

from volcengine.visual.VisualService import VisualService
from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime.types.images.images import SequentialImageGenerationOptions

from conf.system import SYS_CONFIG
from conf.api import API_CONFIG
from src.logger import logger
from src.agents.experts.usage_utils import parse_usage_obj
from server.services.token_usage_service import token_usage_service


async def prompt_enhancement_tool(ctx: InvocationContext, prompt: str) -> AsyncGenerator[str, None]:
    system_prompt = """
你是一个专业的提示词优化专家，精通文生视频领域的提示词具体化和优化工作。
用户会输入初始的视频生成prompt，你需要根据prompt进行润色或扩写。

你的任务分为两种情况：
 - 1. 用户输入了模糊简短的指令（通常为一个简短的不包含任何细节的句子）
    此时你需要根据这些模糊的指令，生成一个更详细、更具创意和高质量的提示词。图像的具体内容细节全都由你来决定，但是需要保持与原始输入指令一致。

 - 2. 用户输入较为详细的指令（通常为超过100词的长句）此时你不需要添加任何画面内容，而是需要对prompt进行润色，你的润色主要集中在以下几个方面：
    **分镜**： 可以对原 prompt 增加更加细致的分镜描述 
    **画面细节**：可以对原始prompt中的细节进行强调
    **特殊元素**：如果原始prompt中存在文字，标志等元素，你需要使其描述更加精确。
    注意！这种情况下你必须保证新生成的prompt与原始prompt严格一致，不能损失或改变任何语义内容，只能润色或强调。

# 注意：
 - 你只需要输出优化后的提示词文本，不要输出md或json对象。
 - 不要指定输出文件的名字，系统会自动命名生成的视频文件。
"""

    def before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
        design_suggestions = callback_context.state.get('design_suggestions', '')
        if design_suggestions and len(design_suggestions) > 0:
            design_suggestions = design_suggestions + f"当前设计专家智能体 ArtKnowledgeAgent 给的设计建议是：{design_suggestions} \n\n"
            design_suggestions = design_suggestions + """注意：这些建议中可能会有多种需要探索的方案，但是你现在需要优化的是其中的一种，
            需要优化的prompt将会在下面描述。你需要关注你需要优化的哪一种，然后参考相建议中对应的细节信息进行优化。不要混淆其他方案中的细节。\n\n"""

            user_prompt = design_suggestions +  f"这是你当前需要优化的 prompt：\n{prompt}。\n请参考 ArtKnowledgeAgent 给的设计建议，对其进行润色或扩写。\n\n"
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
                agent_name="VideoGenerationPromptEnhancementTool",
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
                'message': "LLmAgent调用失败"
            }
            

    except Exception as e:
        error_text = f"LlmAgent出错：{str(e)}"
        logger.error(error_text)
        return {
            'status': 'error',
            'message': error_text
        }


# async def seedance_video_generation_tool(prompt: str) -> AsyncGenerator[dict[str, Any], None]:
#     logger.info("calling seedance for video generation ...")
#     try:
#         ARK_API_KEY = os.environ.get('ARK_API_KEY')
#         client = Ark(
#             base_url="https://ark.cn-beijing.volces.com/api/v3",
#             api_key=ARK_API_KEY,
#         )
#         create_result = client.content_generation.tasks.create(
#             model="doubao-seedance-1-0-pro-250528",
#             content=[
#             ],
#         )
#         task_id = create_result.id
#         while True:
#             get_result = client.content_generation.tasks.get(task_id=task_id)
#             status = get_result.status
#             if status == "succeeded":
#                 logger.info("----- task succeeded -----")
#                 logger.info(get_result)
#                 break
#             elif status == "failed":
#                 logger.info("----- task failed -----")
#                 logger.info(f"Error: {get_result.error}")
#                 break
#             else:
#                 logger.info(f"Current status: {status}, Retrying after 5 seconds...")
#                 time.sleep(5)
#         # ContentGenerationTask(id='cgt-20251019223419-2z5vc', model='doubao-seedance-1-0-pro-250528', status='succeeded', error=None, content=Content(video_url='https://ark-content-generation-cn-beijing.tos-cn-beijing.volces.com/doubao-seedance-1-0-pro/02176088445948500000000000000000000ffffac1908fb70a52a.mp4?X-Tos-Algorithm=TOS4-HMAC-SHA256&X-Tos-Credential=AKLTYWJkZTExNjA1ZDUyNDc3YzhjNTM5OGIyNjBhNDcyOTQ%2F20251019%2Fcn-beijing%2Ftos%2Frequest&X-Tos-Date=20251019T143511Z&X-Tos-Expires=86400&X-Tos-Signature=60c69b80496095abb94b7273e9295d2773c7e590cd98f04bf163ca3b6548b373&X-Tos-SignedHeaders=host', last_frame_url=None), usage=Usage(completion_tokens=246840, total_tokens=246840), created_at=1760884459, updated_at=1760884511, seed=36134, revised_prompt=None, resolution='1080p', ratio='16:9', duration=5, framespersecond=24)
#         video_url = get_result.content.video_url
#         with urllib.request.urlopen(video_url) as response:
#             video_binary_data = response.read()
#             # binary_data now contains the content of the URL as bytes
#             logger.info(f"Successfully read {len(video_binary_data)} bytes from the URL.")
#             # You can now process or save this binary_data
#             # with open('test_vidoe.mp4', 'wb') as f:
#             #     f.write(binary_data)
#             result = {'status': "success", "message": video_binary_data}
#             return result
#     except urllib.error.URLError as e:
#         error_msg = f"Error accessing URL: {e.reason}"
#         return {"status": "error", "message": error_msg}
#     except Exception as e:
#         error_msg = f"An unexpected error occurred: {e}"
#         return {"status": "error", "message": error_msg}


# def encode_media(file_path: str):
#     mime_type, _ = mimetypes.guess_type(file_path)
#     if mime_type is None:
#         mime_type = "application/octet-stream"
#     with open(file_path, 'rb') as f:
#         file_content = f.read()
#     base64_data = base64.b64encode(file_content).decode('utf-8')
#     return f"data:{mime_type};base64,{base64_data}"

async def seedance_video_generation_tool(prompt: str, input_img_list: list, mode: str, aspect_ratio: str = '16:9') -> AsyncGenerator[dict[str, Any], None]:
    """Generate a video with Seedance from prompt and optional image references."""

    logger.info("calling seedance for video generation ...")

    try:
        ARK_API_KEY = os.environ.get('ARK_API_KEY')
        client = Ark(
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=ARK_API_KEY,
        )
        model_name = "doubao-seedance-1-0-pro-250528"
        if mode == 'prompt':
            create_result = client.content_generation.tasks.create(
                model=model_name,
                content=[
                    {"type": "text", "text": prompt},
                ],
            )
        elif mode == 'first_frame':
            create_result = client.content_generation.tasks.create(
                model=model_name,
                content=[
                    {
                        "text": prompt,
                        "type": "text"
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": input_img_list[0]}
                    }
                ]
            )
        elif mode == 'first_frame_and_last_frame':
            create_result = client.content_generation.tasks.create(
                model=model_name,
                content=[
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": input_img_list[0]
                        },
                        "role": "first_frame"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": input_img_list[1]
                        },
                        "role": "last_frame"
                    }
                ]
            )
        elif mode == 'reference_asset':
            model_name = "doubao-seedance-1-0-lite-i2v-250428"
            content = [
                {
                    "type": "text",
                    "text": prompt
                }]
            for img in input_img_list:
                img_dict = {
                    "type": "image_url",
                    "image_url": {
                        "url": img,
                    },
                    "role": "reference_image"
                }
                content.append(img_dict)
            create_result = client.content_generation.tasks.create(
                model=model_name,
                content=content)
        else:
            logger.error("[veo_video_generation_tool] failed: wrong mode")
            return {
                "status": "error",
                "message": "wrong mode",
                "provider": "seedance",
                "model_name": model_name,
                "usage": None,
            }


        task_id = create_result.id
        while True:
            get_result = client.content_generation.tasks.get(task_id=task_id)
            status = get_result.status
            if status == "succeeded":
                logger.info("----- task succeeded -----")
                logger.info(get_result)
                break
            elif status == "failed":
                logger.info("----- task failed -----")
                logger.info(f"Error: {get_result.error}")
                break
            else:
                logger.info(f"Current status: {status}, Retrying after 5 seconds...")
                time.sleep(5)

        # ContentGenerationTask(id='cgt-20251019223419-2z5vc', model='doubao-seedance-1-0-pro-250528', status='succeeded', error=None, content=Content(video_url='https://ark-content-generation-cn-beijing.tos-cn-beijing.volces.com/doubao-seedance-1-0-pro/02176088445948500000000000000000000ffffac1908fb70a52a.mp4?X-Tos-Algorithm=TOS4-HMAC-SHA256&X-Tos-Credential=AKLTYWJkZTExNjA1ZDUyNDc3YzhjNTM5OGIyNjBhNDcyOTQ%2F20251019%2Fcn-beijing%2Ftos%2Frequest&X-Tos-Date=20251019T143511Z&X-Tos-Expires=86400&X-Tos-Signature=60c69b80496095abb94b7273e9295d2773c7e590cd98f04bf163ca3b6548b373&X-Tos-SignedHeaders=host', last_frame_url=None), usage=Usage(completion_tokens=246840, total_tokens=246840), created_at=1760884459, updated_at=1760884511, seed=36134, revised_prompt=None, resolution='1080p', ratio='16:9', duration=5, framespersecond=24)

        video_url = get_result.content.video_url

        with urllib.request.urlopen(video_url) as response:
            video_binary_data = response.read()
            # binary_data now contains the content of the URL as bytes
            logger.info(f"Successfully read {len(video_binary_data)} bytes from the URL.")
            # You can now process or save this binary_data

            # with open('test_vidoe.mp4', 'wb') as f:
            #     f.write(binary_data)
            result = {
                'status': "success",
                "message": video_binary_data,
                "provider": "seedance",
                "model_name": model_name,
                "usage": parse_usage_obj(get_result),
            }
            return result

    except urllib.error.URLError as e:
        error_msg = f"Error accessing URL: {e.reason}"
        logger.error("[seedance_video_generation_tool] failed: {}", e, exc_info=True)
        return {
            "status": "error",
            "message": error_msg,
            "provider": "seedance",
            "model_name": "doubao-seedance-1-0-pro-250528",
            "usage": None,
        }
    except Exception as e:
        error_msg = f"An unexpected error occurred: {e}"
        logger.error("[seedance_video_generation_tool] failed: {}", e, exc_info=True)
        return {
            "status": "error",
            "message": error_msg,
            "provider": "seedance",
            "model_name": "doubao-seedance-1-0-pro-250528",
            "usage": None,
        }



def get_image_obj(file_path):
    with open(file_path, 'rb') as f:
        first_frame_bytes = f.read()
    mime_type, _ = mimetypes.guess_type(file_path)
    image = types.Image(image_bytes=first_frame_bytes, mime_type=mime_type)
    return image


async def veo_video_generation_tool(prompt: str, input_img_list: list, mode: str, aspect_ratio: str = '16:9') -> AsyncGenerator[dict[str, Any], None]:
    """Generate a video with Veo from prompt and optional image references."""
    #
    logger.info("calling veo for video generation ...")

    try:
        client = genai.Client()
        model_name = "veo-3.1-generate-preview"

        if mode == 'prompt':
            operation = client.models.generate_videos(
                model=model_name,
                source=types.GenerateVideosSource(
                    prompt=prompt,
                )
            )
        elif mode == 'first_frame':
            operation = client.models.generate_videos(
                model=model_name,
                source=types.GenerateVideosSource(
                    prompt=prompt,
                    image=input_img_list[0]
                ),
                config=types.GenerateVideosConfig(
                    aspect_ratio=aspect_ratio,
                )
            )
        elif mode == 'first_frame_and_last_frame':
            operation = client.models.generate_videos(
                model=model_name,
                source=types.GenerateVideosSource(
                    prompt=prompt,
                    image=input_img_list[0],
                ),
                config=types.GenerateVideosConfig(
                    last_frame=input_img_list[1],
                    aspect_ratio=aspect_ratio
                ),
            )

        elif mode == 'reference_asset':
            ref_img_list = [types.VideoGenerationReferenceImage(img, reference_type="asset") for img in input_img_list]
            operation = client.models.generate_videos(
                model=model_name,
                source=types.GenerateVideosSource(
                    prompt=prompt,
                ),
                config=types.GenerateVideosConfig(
                    reference_images=ref_img_list,
                    # aspect_ratio=aspect_ratio,
                ),
            )
        elif mode == 'reference_style': #  mode == 'reference_style'
            ref_img_list = [types.VideoGenerationReferenceImage(img, reference_type="style") for img in input_img_list]
            operation = client.models.generate_videos(
                model=model_name,
                source=types.GenerateVideosSource(
                    prompt=prompt,
                ),
                config=types.GenerateVideosConfig(
                    reference_images=ref_img_list,
                    aspect_ratio=aspect_ratio
                ),
            )
        else:
            logger.error("[veo_video_generation_tool] failed: wrong mode")
            return {
                "status": "error",
                "message": "wrong mode",
                "provider": "gemini",
                "model_name": model_name,
                "usage": None,
            }

        # Poll the operation status until the video is ready.
        while not operation.done:
            logger.info("Waiting for video generation to complete...")
            time.sleep(10)
            operation = client.operations.get(operation)

        # Download the generated video.
        res_dict = operation.response.model_dump()
        if 'rai_media_filtered_reasons' in res_dict and res_dict['rai_media_filtered_reasons'] is not None:
            error_list = operation.response.rai_media_filtered_reasons
            error_msg = 'None'
            if error_list and isinstance(error_list, list):
                error_msg = '\n'.join(error_list)
            logger.error(f"[veo_video_generation_tool] failed: {error_msg}")
            return {"status": "error", "message": error_msg}

        else:
            generated_video = operation.response.generated_videos[0]
            video_bytes = client.files.download(file=generated_video.video)
            # generated_video.video.save("realism_example.mp4")
            # print("Generated video saved to realism_example.mp4")

            # ContentGenerationTask(id='cgt-20251019223419-2z5vc', model='doubao-seedance-1-0-pro-250528', status='succeeded', error=None, content=Content(video_url='https://ark-content-generation-cn-beijing.tos-cn-beijing.volces.com/doubao-seedance-1-0-pro/02176088445948500000000000000000000ffffac1908fb70a52a.mp4?X-Tos-Algorithm=TOS4-HMAC-SHA256&X-Tos-Credential=AKLTYWJkZTExNjA1ZDUyNDc3YzhjNTM5OGIyNjBhNDcyOTQ%2F20251019%2Fcn-beijing%2Ftos%2Frequest&X-Tos-Date=20251019T143511Z&X-Tos-Expires=86400&X-Tos-Signature=60c69b80496095abb94b7273e9295d2773c7e590cd98f04bf163ca3b6548b373&X-Tos-SignedHeaders=host', last_frame_url=None), usage=Usage(completion_tokens=246840, total_tokens=246840), created_at=1760884459, updated_at=1760884511, seed=36134, revised_prompt=None, resolution='1080p', ratio='16:9', duration=5, framespersecond=24)

            logger.info(f"Successfully read {len(video_bytes)} bytes from the URL.")
            usage = parse_usage_obj(operation.response) or parse_usage_obj(operation)
            result = {
                'status': "success",
                "message": video_bytes,
                "provider": "gemini",
                "model_name": model_name,
                "usage": usage,
            }
            return result

    except Exception as e:
        error_msg = f"An unexpected error occurred: {e}"
        logger.error("[veo_video_generation_tool] failed: {}", e, exc_info=True)
        return {
            "status": "error",
            "message": error_msg,
            "provider": "gemini",
            "model_name": "veo-3.1-generate-preview",
            "usage": None,
        }
