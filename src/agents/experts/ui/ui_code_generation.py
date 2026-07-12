import io
import zipfile
from typing import AsyncGenerator, List
import json

# from google.adk.agents import LlmAgent
from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.tools import ToolContext
from google.adk.agents.callback_context import CallbackContext
from google.adk.sessions import InMemorySessionService
from google.adk.models import LlmRequest
from src.llm.model_factory import build_model_and_config
from google.genai.types import Blob, Content, Part

from conf.system import SYS_CONFIG
from src.logger import logger
from src.utils import clean_json_string

from src.agents.experts.ui.search import query_2_design


def build_html_zip_bytes(html_content: str) -> bytes:
    """Package generated HTML into an in-memory zip archive."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.html", html_content)
    return buffer.getvalue()

async def ui_code_generation_before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
    """Add session state and artifact context to the model request before generation."""
    current_parameters = callback_context.state.get('current_parameters', {})

    input_text = f"用户输入的任务是：{current_parameters['task_query']}\n"
    llm_request.contents.append(Content(role='user', parts=[Part(text=input_text)]))

    keywords = callback_context.state.get('ui/keyword_extractor_output', {})
    if len(keywords) > 0 and isinstance(keywords, str):
        keywords_clean = clean_json_string(keywords)
        keywords_dict = json.loads(keywords_clean)
        logger.info(keywords_dict)

        product_type_keywords = keywords_dict.get('product_type_keywords', [])
        product_type_keywords = ' '.join(product_type_keywords)

        style_keywords = keywords_dict.get('style_keywords', [])
        style_keywords = ' '.join(style_keywords)

        industry_keywords = keywords_dict.get('industry_keywords', [])
        industry_keywords = ' '.join(industry_keywords)

        stack_keywords = keywords_dict.get('stack_keywords', [])
        stack_keywords = ' '.join(stack_keywords)

        project_name = keywords_dict.get('project_name', '')

        query = product_type_keywords + ' ' + style_keywords + ' ' + industry_keywords + ' ' + stack_keywords
        design = query_2_design(query, project_name)

        input_text = f"针对这个任务，专家智能体给出的设计是：{design}\n"
        logger.info(input_text)
        llm_request.contents.append(Content(role='user', parts=[Part(text=input_text)]))


    return


class UICodeGenerationAgent(BaseAgent):
    model_config = {"arbitrary_types_allowed": True}
    llm: LlmAgent

    def __init__(
            self,
            name: str,
            description: str = '',
            llm_model: str = ''
    ):
        if not llm_model:
            llm_model = SYS_CONFIG.html_gen_llm_model
        logger.info(f"UICodeGenerationAgent: using llm: {llm_model}")

        llm_model, llm_config = build_model_and_config(llm_model)

        llm = LlmAgent(
            name=name,
            model=llm_model,
            generate_content_config=llm_config,
            include_contents='none',
            description=description,
            instruction=ui_code_instruction,
            before_model_callback=ui_code_generation_before_model_callback,
            output_key='ui/code_output'
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
            message = "UICodeGenerationAgent 生成回复失败"
            message_for_user = "生成回复失败"
            logger.error(message)
            current_output = {"author": self.name, 'status': 'error', 'message': message,
                              'message_for_user': message_for_user, 'output_text': ''}
        else:
            message = "已完成UI 生成和相关信息总结"
            message_for_user = "已完成UI生成相关信息总结"
            output_text = '\n'.join(text_list)
            artifact_name = f"step{ctx.session.state.get('step', 0) + 1}_ui_html_bundle.zip"
            artifact_part = Part(
                inline_data=Blob(
                    mime_type="application/zip",
                    data=build_html_zip_bytes(output_text),
                )
            )
            await ctx.artifact_service.save_artifact(
                app_name=ctx.session.app_name,
                user_id=ctx.session.user_id,
                session_id=ctx.session.id,
                filename=artifact_name,
                artifact=artifact_part,
            )
            current_output = {"author": self.name, 'status': 'success', 'message': message,
                              'message_for_user': message_for_user, 'output_text': output_text,
                              'output_artifacts': [
                                  {
                                      'name': artifact_name,
                                      'description': "ZIP package containing generated UI HTML.",
                                  }
                              ]}

        yield Event(
            author='UICodeGenerationAgent',
            content=Content(role='model', parts=[Part(text=message)]),
            actions=EventActions(state_delta={'current_output': current_output})
        )


ui_code_instruction = """
你是一个专业的 UI 设计师，擅长生成UI代码。

# 任务输入
 - 输入的文本：来自某个用户的任务的描述以及设计

# 任务输出
 - 实现这个设计的代码，没有特殊指明，可以使用 html-tailwind

# 注意事项
## 输出格式的注意事项
 - 只输出代码，不要有任何的解释
 - UI界面的语言与任务描述的语言一致，除非用户特别另外指明。

## Pre-Delivery Checklist

Before delivering UI code, verify these items:

### Visual Quality
- [ ] No emojis used as icons (use SVG instead)
- [ ] All icons from consistent icon set (Heroicons/Lucide)
- [ ] Brand logos are correct (verified from Simple Icons)
- [ ] Hover states don't cause layout shift
- [ ] Use theme colors directly (bg-primary) not var() wrapper

### Interaction
- [ ] All clickable elements have `cursor-pointer`
- [ ] Hover states provide clear visual feedback
- [ ] Transitions are smooth (150-300ms)
- [ ] Focus states visible for keyboard navigation

### Light/Dark Mode
- [ ] Light mode text has sufficient contrast (4.5:1 minimum)
- [ ] Glass/transparent elements visible in light mode
- [ ] Borders visible in both modes
- [ ] Test both modes before delivery

### Layout
- [ ] Floating elements have proper spacing from edges
- [ ] No content hidden behind fixed navbars
- [ ] Responsive at 375px, 768px, 1024px, 1440px
- [ ] No horizontal scroll on mobile

### Accessibility
- [ ] All images have alt text
- [ ] Form inputs have labels
- [ ] Color is not the only indicator
- [ ] `prefers-reduced-motion` respected

下面开始任务
"""
