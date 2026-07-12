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


async def ui_keyword_extractor_before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
    """Add session state and artifact context to the model request before generation."""
    current_parameters = callback_context.state.get('current_parameters', {})

    input_text = f"用户输入的任务是：{current_parameters['task_query']}\n"
    llm_request.contents.append(Content(role='user', parts=[Part(text=input_text)]))

    return


class UIKeywordsExtractorAgent(BaseAgent):
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
        logger.info(f"UIKeywordsExtractorAgent: using llm: {llm_model}")

        llm_model, llm_config = build_model_and_config(llm_model)

        llm = LlmAgent(
            name=name,
            model=llm_model,
            generate_content_config=llm_config,
            include_contents='none',
            description=description,
            instruction=ui_keyword_extractor_instruction,
            before_model_callback=ui_keyword_extractor_before_model_callback,
            output_key='ui/keyword_extractor_output'
        )

        super().__init__(
            name=name,
            description=description,
            llm=llm,
        )

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Run the agent asynchronously and yield ADK events."""
        current_parameters = ctx.session.state.get('current_parameters', {})
        if 'task_query' not in current_parameters:
            error_text = f"提供给{self.name}的参数缺失，必须包含：task_query"
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
            message = "UIKeywordsExtractorAgent 生成回复失败"
            message_for_user = "生成回复失败"
            logger.error(message)
            current_output = {"author": self.name, 'status': 'error', 'message': message,
                              'message_for_user': message_for_user, 'output_text': ''}
        else:
            message = "已完成UI需求分析和相关信息总结"
            message_for_user = "已完成UI需求分析和相关信息总结"
            output_text = '\n'.join(text_list)
            current_output = {"author": self.name, 'status': 'success', 'message': message,
                              'message_for_user': message_for_user, 'output_text': output_text}

        yield Event(
            author='UIKeywordsExtractorAgent',
            content=Content(role='model', parts=[Part(text=message)]),
            actions=EventActions(state_delta={'current_output': current_output})
        )


ui_keyword_extractor_instruction = """
你是一个专业的文本分析、提取和总结专家。

你的任务是分析一段文本，并提取相关的关键词。这段文本是来自一个用户输入的任务描述，是一段下发给UI界面生成智能体的任务。用来描述希望UI生成智能体针对某个行业的某种类型的产品，生成某种风格的UI界面。
提取的关键词会被用来从私有的数据库中检索相关的完成任务需要的参数设定信息。

# 任务输入
 - 输入的文本：来自某个用户的任务的描述

# 任务输出
你需要从输入的文本中提取4个方面的关键词：产品类型、希望的UI的风格 、 产品所属的行业 和 技术栈的要求。

输出需要是 JSON 格式的，字段如下所示：
 - `product_type_keywords`: 字数串列表，里面放提取的和产品类型相关的关键词， 比如SaaS, e-commerce, portfolio, dashboard, landing page, 等.
 - `style_keywords`: 字数串列表，里面放提取的风格相关的关键词，比如minimal, playful, professional, elegant, dark mode, 等
 - `industry_keywords`: 字数串列表，里面放提取的相关行业的关键词，比如healthcare, fintech, gaming, education, 等
 - `stack_keywords`: 字数串列表，里面放和技术栈相关的关键词，比如React, Vue, Next.js等, 默认 `html-tailwind`。
 - `project_name`: 字符串，你给这个用户的需求的 project 起的名字。


# 特别注意
1. 不要有信息方面的遗漏
2. 不要输出文本里面没有的内容，如果输入文本没有给到你，相关字段不要填写。
3. 如果用户输入的文本不是英文的，你需要在json里面用对应的英文表示。


下面开始任务
"""

