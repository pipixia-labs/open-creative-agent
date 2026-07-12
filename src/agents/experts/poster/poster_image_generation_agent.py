from typing import AsyncGenerator, List, Dict, Any
from typing_extensions import override
import time
import asyncio
from PIL import Image
import io
from io import BytesIO
import json
import re


from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.callback_context import CallbackContext
from google.adk.events import Event, EventActions
from google.adk.models import LlmRequest
from google.adk.tools import ToolContext
from google.adk.tools import google_search
from google.genai.types import Part, Blob, Content
from google.genai import types

from src.logger import logger
from src.agents.experts.image_generation_reasoning.tool import nano_banana_image_generation_tool

from src.agents.experts.image_utils import get_image_info_from_bytes
from src.utils import clean_json_string
from src.agents.experts.image_utils import make_background_transparent_bytes
from src.agents.experts.image_utils import select_aspect_ratio
from src.agents.experts.usage_utils import parse_usage_obj
from server.services.token_usage_service import token_usage_service

async def nano_banana_image_generation_tool(
    ctx: InvocationContext,
    ref_image,
    prompt: str,
    aspect_ratio="16:9",
    resolution="1K",
) -> AsyncGenerator[
    dict[str, Any], None]:
    # aspect_ratio = "16:9"  # "1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9"
    # resolution = "2K"  # "1K", "2K", "4K"
    logger.info("calling nano banana for PPT generation ...")
    aspect_ratio = select_aspect_ratio(aspect_ratio)

    try:
        input_images: list[Image.Image] = []
        if ref_image is None:
            input_images = []
        elif isinstance(ref_image, list):
            input_images = ref_image
        else:
            if len(ref_image) > 10:
                ref_image = ref_image[:5] + ref_image[-5:]
            input_images = ref_image

        def before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
            user_parts: list[Part] = [Part(text=prompt)]
            for img in input_images:
                if isinstance(img, Image.Image):
                    buffer = BytesIO()
                    img.save(buffer, format="PNG")
                    user_parts.append(
                        Part(inline_data=Blob(mime_type="image/png", data=buffer.getvalue()))
                    )
            llm_request.contents.append(Content(role="user", parts=user_parts))

        llm = LlmAgent(
            name="poster_image_generation_nano_banana",
            model="gemini-3.1-flash-image-preview",
            instruction="Generate images according to the user prompt and optional reference images.",
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

        result = {'status': "success", "message": []}
        text_message = ''
        img_message = []
        ime_message_len = []
        total_len = 0
        len_str = ""
        img_index = 0
        usage = None
        async for event in llm.run_async(ctx):
            parsed_usage = parse_usage_obj(event)
            if parsed_usage:
                usage = parsed_usage
            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                if part.text is not None:
                    text_message = part.text
                elif part.inline_data is not None:
                    img_message.append(part.inline_data.data)
                    ime_message_len.append(len(part.inline_data.data))
                    total_len = total_len + len(part.inline_data.data)
                    len_str = len_str +  f"图像{img_index}的大小为:{len(part.inline_data.data)}\n"

        if len(img_message) > 0 and total_len > 0:
            result = {
                'status': "success",
                "image_bytes_list": img_message,
                "provider": "gemini",
                "model_name": "gemini-3.1-flash-image-preview",
                "usage": usage,
            }
            logger.info(f"nano_banana image generation completed. bytes={len_str}")
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

class PosterImageGenerationAgent(BaseAgent):
    """Generate image assets for poster workflows from prompts and optional references."""
    model_config = {"arbitrary_types_allowed": True}

    def __init__(
            self, name: str, description: str = "") -> None:
        """Initializes the ImageGenerationAgent."""

        sub_agents_list: List[BaseAgent] = []
        super().__init__(
            name=name,
            sub_agents=sub_agents_list,
            description=description,
        )

    def format_event(self, content_text: str = None, state_delta: Dict = None):
        event = Event(author=self.name)
        if state_delta:
            event.actions = EventActions(state_delta=state_delta)
        if content_text:
            event.content = Content(role='model', parts=[Part(text=content_text)])
        return event

    @override
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """
        Args:
            ctx (InvocationContext): The invocation context for the agent.
        Yields:
            Event: The events generated by the sequential agent during the image generation process.
        """

        current_parameters = ctx.session.state.get('current_parameters', {})
        logger.info(current_parameters)
        draft_results = ctx.session.state.get('poster_generation/draft_results_v2', {})
        logger.info(draft_results)
        if isinstance(draft_results, str):
            draft_results = clean_json_string(draft_results)
            logger.info(draft_results)
            draft_results = json.loads(draft_results)
        # logger.info(draft_results)
        #     current_output = {"author": self.name, "status": "error", "message": error_text, 'output_text': ''}
        #     logger.error(error_text)
        #
        #     yield self.format_event(error_text, {"current_output": current_output})
        #     return

        reference_image_name = current_parameters.get('reference_image_name', '')
        img_obj = None
        if isinstance(reference_image_name, str) and len(reference_image_name) > 0:
            image_art_part = await ctx.artifact_service.load_artifact(filename=reference_image_name,
                                                                     app_name=ctx.session.app_name,
                                                                     user_id=ctx.session.user_id,
                                                                     session_id=ctx.session.id)
            img_obj = Image.open(BytesIO(image_art_part.inline_data.data))
        elif isinstance(reference_image_name, list):
            img_obj = []
            for image_name in reference_image_name:
                image_art_part = await ctx.artifact_service.load_artifact(filename=image_name,
                                                                          app_name=ctx.session.app_name,
                                                                          user_id=ctx.session.user_id,
                                                                          session_id=ctx.session.id)
                img_obj.append(Image.open(BytesIO(image_art_part.inline_data.data)))

        logger.info(img_obj)
        image_to_generate = draft_results.get('poster_image_to_generate', [])
        logger.info(f'{len(image_to_generate)} images to generate')
        logger.info(image_to_generate)

        result_image_list = []
        output_artifacts = []
        message = []

        img_info_to_generate = []
        as_set = set()
        need_transparent = False
        for i, img_info in enumerate(image_to_generate):
            aspect_ratio = "1:1"
            resolution = "1K"
            # description = ''
            if 'aspect_ratio' in img_info:
                aspect_ratio = img_info['aspect_ratio']
                aspect_ratio = select_aspect_ratio(aspect_ratio)
            if 'resolution' in img_info:
                resolution = img_info['resolution']
            if 'description' in img_info:
                description = img_info['description']
                p =  f'配图{i}的提示词：' + description + '\n'
            if 'file_name_placeholder' in img_info:
                file_name_placeholder = img_info['file_name_placeholder']

            if 'Transparent_Background' in p:
                need_transparent = True
            temp_info = (p, aspect_ratio, resolution, file_name_placeholder)
            img_info_to_generate.append(temp_info)
            as_set.add(aspect_ratio)

        parallel_mode = False
        if len(as_set) == 1 and (not need_transparent):
            parallel_mode = True

        parallel_mode = False
        if parallel_mode:
            if img_obj is None or len(img_obj) == 0:
                prompt_all = f"你需要为一个海报配图，如下是这些图像的提示词。尤其需要注意的是图像上的文字需要符合prompt的要求，不要出现类似比例、参数的不该出现的信息。你需要生成{len(img_info_to_generate)}个单独的图像。\n"
            else:
                prompt_all = f"你的任务是参考一个或多个指定的图像来为一个海报配图。尤其需要注意的是图像上的文字需要符合prompt的要求，不要出现类似比例、参数的不该出现的信息。如下是这些需要生成的插图的提示词。你需要生成{len(img_info_to_generate)}个单独的图像。\n"

            for info in img_info_to_generate:
                prompt_all = prompt_all + info[0]

            logger.info("Calling nano_banana once for batch image generation.")
            logger.info(prompt_all)
            logger.info(aspect_ratio)
            results = await nano_banana_image_generation_tool(ctx, img_obj, prompt_all, aspect_ratio=aspect_ratio, resolution="2K")
            if isinstance(results.get("usage"), dict):
                await token_usage_service.record_external_usage(
                    user_id=ctx.session.user_id,
                    session_id=ctx.session.id,
                    component="expert_tool",
                    agent_name=self.name,
                    model_name=results.get("model_name"),
                    usage=results["usage"],
                )

            if results['status'] == 'success':
                logger.info(f'Generated image count: {len(results["image_bytes_list"])}')

                for img_index, img_bytes in enumerate(results["image_bytes_list"]):
                    message.append(f"Image {img_index + 1} generated successfully")
                    file_name_placeholder = img_info_to_generate[img_index][3]
                    prompt = img_info_to_generate[img_index][0]

                    if file_name_placeholder:
                        file_name_placeholder_remove_dot = file_name_placeholder.replace('.', '_')  ## abc.png -> abc_png
                        artifact_name = f"step{ctx.session.state.get('step') + 1}_poster_image_generation_output{img_index}_{file_name_placeholder_remove_dot}.png"
                    else:
                        artifact_name = f"step{ctx.session.state.get('step') + 1}_poster_image_generation_output{img_index}.png"

                    artifact_part = Part(inline_data=Blob(mime_type='image/png', data=img_bytes))
                    await ctx.artifact_service.save_artifact(
                        app_name=ctx.session.app_name, user_id=ctx.session.user_id, session_id=ctx.session.id,
                        filename=artifact_name, artifact=artifact_part
                    )

                    basic_info = get_image_info_from_bytes(img_bytes)
                    description = (
                        f"Image {img_index + 1} generated at step {ctx.session.state.get('step') + 1}. "
                        f"HTML placeholder: {file_name_placeholder}. Prompt: {prompt}\n\n"
                        f"Generated image metadata: {basic_info}"
                    )
                    output_artifacts.append({'name': artifact_name, 'placeholder_name': file_name_placeholder, 'description': description})
            else:
                message.append(f"Batch image generation failed: {results['message']}. Falling back to single calls.")
                parallel_mode = False


        if not parallel_mode:
            if img_obj is None or len(img_obj) == 0:
                pre_prompt = "你的任务是根据提示词生成一个新的图像。"
            else:
                pre_prompt = "你的任务是参考一个或多个指定的图像，来根据提示词生成一个新的图像。"

            for i, img_info in enumerate(image_to_generate):
                aspect_ratio = "1:1"
                resolution = "1K"
                prompt = pre_prompt
                # description = ''
                if 'aspect_ratio' in img_info:
                    aspect_ratio = img_info['aspect_ratio']
                if 'resolution' in img_info:
                    resolution = img_info['resolution']
                if 'description' in img_info:
                    description = img_info['description']
                    prompt = prompt +  '按照如下的描述来生成图像：' + description + '\n'
                if 'file_name_placeholder' in img_info:
                    file_name_placeholder = img_info['file_name_placeholder']

                logger.info('*'*30 + f'  {i}    ' + '*'*30)
                logger.info(prompt)
                if img_obj is not None:
                    logger.info(f"Reference image count: {len(img_obj)}")
                results = await nano_banana_image_generation_tool(ctx, img_obj, prompt, aspect_ratio=aspect_ratio, resolution=resolution)
                if isinstance(results.get("usage"), dict):
                    await token_usage_service.record_external_usage(
                        user_id=ctx.session.user_id,
                        session_id=ctx.session.id,
                        component="expert_tool",
                        agent_name=self.name,
                        model_name=results.get("model_name"),
                        usage=results["usage"],
                    )


                # print(results)
                if results['status'] == 'error':
                    message.append(f"逐个图片生成失败，原因：{results['message']}")
                else:
                    img_bytes = results['image_bytes_list'][0]
                    if img_obj is None:
                        img_obj = []
                    img_obj.append(Image.open(BytesIO(img_bytes)))

                    if 'TRANSPARENT_BACKGROUND' in prompt:
                        for _ in range(4):
                            img_bytes_result = make_background_transparent_bytes(img_bytes)
                            if len(img_bytes_result) > 0:
                                img_bytes = img_bytes_result
                                break

                    message.append(f"第{i + 1}个图片生成成功")
                    if file_name_placeholder:
                        file_name_placeholder_remove_dot = file_name_placeholder.replace('.', '_') ## abc.png -> abc_png
                        artifact_name = f"step{ctx.session.state.get('step') + 1}_poster_image_generation_output{i}_{file_name_placeholder_remove_dot}.png"
                    else:
                        artifact_name = f"step{ctx.session.state.get('step') + 1}_poster_image_generation_output{i}.png"

                    artifact_part = Part(inline_data=Blob(mime_type='image/png', data=img_bytes))
                    await ctx.artifact_service.save_artifact(
                        app_name=ctx.session.app_name, user_id=ctx.session.user_id, session_id=ctx.session.id,
                        filename=artifact_name, artifact=artifact_part
                    )

                    basic_info = get_image_info_from_bytes(img_bytes)

                    description = f"第{ctx.session.state.get('step') + 1}步由图片生成工具生成的第{i + 1}张图片，在html代码中的文件名为：{file_name_placeholder}，prompt为：{prompt} \n\n 生成后的图像基本信息为：{basic_info}"

                    output_artifacts.append({'name': artifact_name, 'placeholder_name': file_name_placeholder, 'description': description})

        if len(output_artifacts) == 0 and len(image_to_generate) > 0:
            message = f"图片生成失败。{','.join(message)}"
            message_for_user = message
            logger.error(message)
            current_output = {"author": self.name, 'status': 'error', 'message': message,
                              'message_for_user': message_for_user, 'output_text': ''}

        else:
            message = f"已完成图像生成：{','.join(message)}"
            message_for_user = f"已完成图像生成工作。"
            logger.info(message)
            current_output = {"author": self.name, 'status': 'success', 'message': message,
                              'message_for_user': message_for_user, 'output_artifacts': output_artifacts,
                              'output_text': ''}

        yield self.format_event(message, {"poster_image_generation_results": current_output})
        return
