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


async def extractor_before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
    """Add session state and artifact context to the model request before generation."""
    current_parameters = callback_context.state.get('current_parameters', {})
    long_text_to_extract = callback_context.state.get('long_text_to_extract', '')

    input_text = f"当前的任务是：{current_parameters['task_query']}\n需要处理的长文本是：{long_text_to_extract}"
    llm_request.contents.append(Content(role='user', parts=[Part(text=input_text)]))

    return


class ExtractorAgent(BaseAgent):
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
        logger.info(f"ExtractorAgent: using llm: {llm_model}")

        llm_model, llm_config = build_model_and_config(llm_model)

        llm = LlmAgent(
            name=name,
            model=llm_model,
            generate_content_config=llm_config,
            include_contents='none',
            description=description,
            instruction=extractor_instruction,
            before_model_callback=extractor_before_model_callback,
            output_key='long_context_summerization'
        )

        super().__init__(
            name=name,
            description=description,
            llm=llm,
        )

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Run the agent asynchronously and yield ADK events."""
        current_parameters = ctx.session.state.get('current_parameters', {})
        if 'task_query' not in current_parameters or 'search_result' not in current_parameters:
            error_text = f"提供给{self.name}的参数缺失，必须包含：task_query 和 search_result"
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
            message = "ExtractorAgent 生成回复失败"
            message_for_user = "生成回复失败"
            logger.error(message)
            current_output = {"author": self.name, 'status': 'error', 'message': message, 'message_for_user':message_for_user, 'output_text':''}
        else:
            message = "已完成长文本分析和相关信息总结"
            message_for_user = "已完成长文本分析和相关信息总结"
            output_text = '\n'.join(text_list)
            current_output = {"author": self.name, 'status': 'success', 'message': message, 'message_for_user':message_for_user, 'output_text': output_text}

        yield Event(
            author='ExtractorAgent',
            content=Content(role='model', parts=[Part(text=message)]),
            actions=EventActions(state_delta={'current_output': current_output})
        )


extractor_instruction = """
你是一个专业的文本分析、提取和总结专家。

你的任务是根据用户的任务要求，分析一个长文本（一般情况下是搜索的结果，也就是几篇文章），并提取里面和用户任务相关的信息，然后总结输出出来。

你需要逐个处理每个长文，并提取相关的信息。你的任务不是生成一篇文章，而是提取相关的信息。提取之后的信息，会有其他智能体来处理，比如生成文章。

# 任务输入
 - 任务描述：用户的任务的描述
 - 长文本：一般是搜索的结果，几篇文章。可能是用json形式来存放的。

# 任务输出
 - 摘要：和用户任务相关的所有信息。
 - 形式：输出以md格式输出。可以根据用户的任务性质来选择以表格形式总结主要的信息。输出信息的语言需要与用户使用的语言一致。
 
# 任务步骤（严格遵守）
首先你需要理解用户的任务，然后分如下的两个步骤输出：
第一步：先分析用户的任务需求，明确相关的事项
第二步：分析长文本并输出相关信息

# 输出格式
输出一个json，里面包含如下两个字段：
'task_analysis': 放你对当前任务需要的信息的分析
'summerization': 放你从长文本中总结出来的和任务相关的信息


# 特别注意
1. 不要有信息方面的遗漏
2. 不要输出长文本里面没有的内容，如果长文本没有给到你，你如实输出就好。


下面开始任务
"""

