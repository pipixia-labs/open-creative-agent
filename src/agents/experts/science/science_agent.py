# import asyncio
# import uuid
# from typing_extensions import override
import datetime
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

async def science_agent_before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
    """Add session state and artifact context to the model request before generation."""
    current_parameters = callback_context.state.get('current_parameters', {})

    current_prompt = current_parameters['prompt']
    current_info = current_parameters.get('current_info', 'null')
    current_content = Content(role='user', parts=[Part(text=f"当前的任务是：{current_prompt}\n 当前已经收集到的信息是：{current_info}\n")])
    llm_request.contents.append(current_content)

    if len(current_parameters.get('input_img_name', []))==0:
        return
    
    input_img_name = current_parameters.get('input_img_name', [])
    artifact_parts = [Part(text="以下是你可以参考的图片：\n")]
    for i, art_name in enumerate(input_img_name):
        artifact_parts.append(Part(text=f"这是第{i+1}张图片，它的名称是{art_name}"))
        art_part = await callback_context.load_artifact(filename=art_name)
        artifact_parts.append(art_part)
    
    llm_request.contents.append(Content(role='user', parts=artifact_parts))

    return



class ScienceAgent(BaseAgent):
    model_config = {"arbitrary_types_allowed": True}
    llm: LlmAgent

    def __init__(
        self,
        name: str,
        description: str = '',
        llm_model: str = ''
    ):
        if not llm_model:
            llm_model = SYS_CONFIG.science_llm_model
        logger.info(f"ScienceAgent: using llm: {llm_model}")

        # if 'gemini' not in llm_model:
        #     if 'gpt-5' in llm_model:
        #         llm_model = LiteLlm(model=llm_model, extra_body={"reasoning_effort": "low"})
        #     else:
        #         llm_model = LiteLlm(model=llm_model)

        llm_model, llm_config = build_model_and_config(llm_model)

        time_str = datetime.date.today().strftime("%Y-%m-%d")
        llm = LlmAgent(
            name=name,
            model=llm_model,
            generate_content_config=llm_config,
            include_contents='none',
            description=description,
            instruction=science_instruction.format(TIME_STR=time_str),
            before_model_callback=science_agent_before_model_callback
        )
        
        super().__init__(
            name = name,
            description=description,
            llm=llm,
        )

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Run the agent asynchronously and yield ADK events."""
        current_parameters = ctx.session.state.get('current_parameters', {})
        if 'prompt' not in current_parameters:
            error_text = f"提供给{self.name}的参数缺失，必须包含：prompt"
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
            message = "ScienceAgent 生成回复失败"
            message_for_user = "生成回复失败"
            logger.error(message)
            current_output = {"author": self.name, 'status': 'error', 'message': message, 'message_for_user':message_for_user, 'output_text':''}
        else:
            message = "ScienceAgent 已完成方案设计"
            message_for_user = " 已完成当前步骤执行"
            output_text = '\n'.join(text_list)
            current_output = {"author": self.name, 'status': 'success', 'message': message, 'message_for_user':message_for_user, 'output_text': output_text}
        
        yield Event(
            author='ScienceAgent',
            content=Content(role='model', parts=[Part(text=message)]),          
            actions=EventActions(state_delta={'current_output': current_output})
        )

science_instruction = """
你是一个理科、工科、工程方面的天才，擅长数学、物理、化学、生物、计算机等问题的解答。
你会接受用户输入的一个理工科任务，有时还会有数量不等的参考图片。
你的任务是根据任务描述和参考给定信息来输出答案。

# 必要信息
 - 当前时间：{TIME_STR}
 
 
# 任务输入
 - 问题：生成用户描述的理工科相关的任务
 - 图片：数量不等的用于相关的图片，可选项。


# 任务输出
任务的输出为文本，按步骤呈现，易懂。

"""

