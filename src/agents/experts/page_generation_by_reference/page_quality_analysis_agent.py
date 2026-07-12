# import asyncio
# import uuid
# from typing_extensions import override
from typing import AsyncGenerator, List

# from google.adk.agents import LlmAgent
from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.tools import ToolContext
from google.adk.agents.callback_context import CallbackContext
from google.adk.sessions import InMemorySessionService
from google.adk.models import LlmRequest
from src.llm.model_factory import build_model_and_config
from google.genai.types import Part
from google.genai.types import Content

from conf.system import SYS_CONFIG
from src.logger import logger
from src.agents.experts.image_utils import get_image_info_from_bytes


async def pgbr_quality_analysis_before_model_callback(callback_context: CallbackContext,
                                                             llm_request: LlmRequest):
    """Add session state and artifact context to the model request before generation."""
    current_parameters = callback_context.state.get('current_parameters', {})

    if 'task_query' in current_parameters:
        input_text = f"当前的任务是：{current_parameters['task_query']}\n"
        llm_request.contents.append(Content(role='user', parts=[Part(text=input_text)]))

    reference_image_name = current_parameters.get('reference_image_name', '')
    if reference_image_name is not None and len(reference_image_name) > 0:
        art_part = await callback_context.load_artifact(filename=reference_image_name)

        basic_info = get_image_info_from_bytes(art_part.inline_data.data)
        artifact_parts = [Part(text=f"你参考图像的名字为:{reference_image_name}。\n其基本信息为：{basic_info}\n，以下是图片的内容：\n")]

        artifact_parts.append(art_part)
        llm_request.contents.append(Content(role='user', parts=artifact_parts))

    pgbr_html_2_image_result = callback_context.state.get('pgbr_html_2_image_result', {})

    artifact_name = pgbr_html_2_image_result['html_2_image_artifacts'][0]['name']
    image_part = await callback_context.load_artifact(artifact_name)
    if image_part is not None:
        basic_info = get_image_info_from_bytes(image_part.inline_data.data)
        artifact_parts = [Part(text=f"html_to_image智能体生成图像的名字为:{artifact_name}。\n其基本信息为：{basic_info}\n，以下是图片的内容：\n")]
        artifact_parts.append(image_part)
        llm_request.contents.append(Content(role='user', parts=artifact_parts))

    return


class PGBRQualityAnalysisAgent(BaseAgent):
    model_config = {"arbitrary_types_allowed": True}
    llm: LlmAgent

    def __init__(self, name: str, description: str = '', llm_model: str = ''):
        if not llm_model:
            llm_model = SYS_CONFIG.llm_model
        logger.info(f"PGBRQualityAnalysisAgent: using llm: {llm_model}")

        llm_model, llm_config = build_model_and_config(llm_model)

        llm = LlmAgent(
            name=name,
            model=llm_model,
            generate_content_config=llm_config,
            description=description,
            include_contents='none',
            instruction=pgbr_quality_analysis_instruction,
            before_model_callback=pgbr_quality_analysis_before_model_callback,
            output_key="page_generation_by_reference/quality_analysis_results"
        )

        super().__init__(
            name=name,
            description=description,
            llm=llm,
        )

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Run the agent asynchronously and yield ADK events."""
        current_parameters = ctx.session.state.get('current_parameters', {})
        if 'task_query' not in current_parameters or 'reference_image_name' not in current_parameters:
            error_text = f"提供给{self.name}的参数缺失，必须包含：task_query 和 reference_image_name"
            current_output = {"author": self.name, "status": "error", "message": error_text, 'output_text': ''}
            logger.error(error_text)

            yield Event(
                author=self.name,
                content=Content(role='model', parts=[Part(text=error_text)]),
                actions=EventActions(state_delta={"current_output": current_output})
            )
            return

        text_list = []
        async for event in self.llm.run_async(ctx):
            if event.is_final_response() and event.content and event.content.parts:
                generated_text = next((part.text for part in event.content.parts if part.text), None)
                if not generated_text:
                    continue
                yield event
                text_list.append(generated_text)

        if len(text_list) == 0:
            message = f"PGBRQualityAnalysisAgent 生成回复失败"
            message_for_user = "生成回复失败"
            logger.error(message)
            current_output = {"author": self.name, 'status': 'error', 'message': message,
                              'message_for_user': message_for_user, 'output_text': ''}
        else:
            message = f"PGBRQualityAnalysisAgent 已完成分析"
            message_for_user = "已完成分析"
            output_text = '\n'.join(text_list)
            current_output = {"author": self.name, 'status': 'success', 'message': message,
                              'message_for_user': message_for_user, 'output_text': output_text}

        yield Event(
            author='PGBRQualityAnalysisAgent',
            content=Content(role='model', parts=[Part(text=message)]),
            actions=EventActions(state_delta={'current_output': current_output})
        )


pgbr_quality_analysis_instruction = '''
# 角色
你是一个顶尖的视觉设计师，擅长评估给到图像的质量，并给出修改意见。


# 目标

给你的输入如下：
 - 任务描述：智能体的任务的描述，这个任务是参考image_1，根据用户的需求（修改、替换等），来生成image_2。
 - image_1：和任务以及给到的参考图像
 - image_2: 一个智能体参考 image_1 生成结果是 image_2。

你的目标是评估 image_2 的质量，并给出修改意见。

# 需要考虑的因素
你需要考虑如下的相关因素：
 - 你需要考虑每个设计元素是有问题，通常的设计元素包含背景图、前景图、logo、标题、文字区。通常的问题包括：遮挡、显示不完全、布局不美观。
 - 文字区是否有不合理的空白？
 - 哪里破坏了美观

## 设计方法
 - 需要考虑参考图像以及设计元素分析中体现的整体设计效果，设计生成的图像需要在整体和用户心目中的结果（参考图像+任务描述中体现的）一致。具体的需要在图像主体区域、文字信息区域的比例一致。如果图像和文字有改动，你需要想办法来尽量保持比例一致
 - 在整体满足用户心目中图像的要求之后，考虑细节部分，各个图像区域，各个文字区域，需要精细调整位置、大小、相对尺寸比例，使得整体效果美观。不要出现文字过小看不清，装饰性元素过大导致主体不突出，颜色搭配不合理等等问题。

针对你发现的每个问题，都需要提出修改意见，来消除这种瑕疵。


---

下面开始分析和解构任务
'''

