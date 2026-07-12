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


async def read_artifact_before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
    """Add session state and artifact context to the model request before generation."""
    current_parameters = callback_context.state.get('current_parameters', {})
    if 'text_file_to_read' in current_parameters:
        text_file_to_read = current_parameters['text_file_to_read']
        if isinstance(text_file_to_read, str):
            text_file_to_read = [text_file_to_read]

        input_text = f"当前的任务是：{current_parameters['task_query']}\n"
        for txt_file_name in text_file_to_read:
            txt_info_bin = await callback_context.load_artifact(txt_file_name)
            if txt_info_bin is not None:
                txt_info = txt_info_bin.inline_data.data.decode("utf-8")
                input_text = input_text + f"文件：{txt_file_name} 的内容是：\n{txt_info}\n\n"

        llm_request.contents.append(Content(role='user', parts=[Part(text=input_text)]))
    else:
        input_text = f"当前的任务是：{current_parameters['task_query']}\n需要读取的文件未被正确指定。"
        llm_request.contents.append(Content(role='user', parts=[Part(text=input_text)]))

    logger.info(f"ReadArtifactAgent: input_text: {input_text}")

    return


class ReadArtifactAgent(BaseAgent):
    model_config = {"arbitrary_types_allowed": True}
    llm: LlmAgent

    def __init__(
            self,
            name: str,
            description: str = '',
            llm_model: str = ''
    ):
        if not llm_model:
            llm_model = SYS_CONFIG.llm_model
        logger.info(f"ReadArtifactAgent: using llm: {llm_model}")

        llm_model, llm_config = build_model_and_config(llm_model)

        llm = LlmAgent(
            name=name,
            model=llm_model,
            generate_content_config=llm_config,
            include_contents='none',
            description=description,
            instruction=read_artifact_instruction,
            before_model_callback=read_artifact_before_model_callback,
            output_key='read_artifact_results',
        )

        super().__init__(
            name=name,
            description=description,
            llm=llm,
        )

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Run the agent asynchronously and yield ADK events."""
        current_parameters = ctx.session.state.get('current_parameters', {})
        if 'text_file_to_read' not in current_parameters:
            error_text = f"提供给{self.name}的参数缺失，必须包含：text_file_to_read"
            current_output = {"author": self.name, "status": "error", "message": error_text, 'output_text':''}
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
            message = "ReadArtifactAgent 生成回复失败"
            message_for_user = "生成回复失败"
            logger.error(message)
            current_output = {"author": self.name, 'status': 'error', 'message': message, 'message_for_user':message_for_user, 'output_text':''}
        else:
            message = "已完成长文本分析和相关信息总结"
            message_for_user = "已完成长文本分析和相关信息总结"
            output_text = '\n'.join(text_list)
            current_output = {"author": self.name, 'status': 'success', 'message': message, 'message_for_user':message_for_user, 'output_text': output_text}

        yield Event(
            author='ReadArtifactAgent',
            content=Content(role='model', parts=[Part(text=message)]),
            actions=EventActions(state_delta={'current_output': current_output})
        )


read_artifact_instruction = """
你是一个专业的文本处理专家。

你的任务是根据用户的任务要求，处理一个文本文件的任务，一般情况下是从artifact读取的文章文本内容，也就是几篇文章，并处理。

你的任务形式只有两种：
 - 提取里面和用户任务相关的信息，然后总结输出出来
 - 原封不动的输出文件的内容。如果不明确说明，就是复制并输出出来。

# 任务输入
 - 任务描述：用户的任务的描述
 - 长文本：从artifact读取的文章内容，文本形式。
 

# 输出格式
输出文本

# 特别注意
1. 不要有信息方面的遗漏
2. 不要输出给定文本里面没有的内容，你如实输出就好。
3. 遵守用户指令


下面开始任务
"""

