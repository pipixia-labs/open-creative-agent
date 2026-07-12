# import asyncio
# import uuid
# from typing_extensions import override
from typing import AsyncGenerator, List
import datetime

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


async def pgbr_finalize_before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
    """Add session state and artifact context to the model request before generation."""
    current_parameters = callback_context.state.get('current_parameters', {})

    if 'task_query' in current_parameters:
        input_text = f"当前的任务是：{current_parameters['task_query']}\n"
        llm_request.contents.append(Content(role='user', parts=[Part(text=input_text)]))

    now = datetime.datetime.now()
    time_stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    message = f"当前步骤的 time_stamp 是：{time_stamp} \n\n"
    current_content = Content(role='user', parts=[Part(text=message)])
    llm_request.contents.append(current_content)

    reference_image_name = current_parameters.get('reference_image_name', '')
    if reference_image_name is not None and len(reference_image_name) > 0:
        artifact_parts = [Part(text=f"你参考图像的名字为:{reference_image_name}，以下是图片的内容：\n")]
        art_part = await callback_context.load_artifact(filename=reference_image_name)
        artifact_parts.append(art_part)
        llm_request.contents.append(Content(role='user', parts=artifact_parts))

    draft_results = callback_context.state.get('page_generation_by_reference/draft_results', {})
    logger.info(f"draft_results: {draft_results}")
    if len(draft_results) > 0:
        input_text = f"当前的海报的设计草稿为：{draft_results}\n"
        llm_request.contents.append(Content(role='user', parts=[Part(text=input_text)]))

    input_img_name = current_parameters.get('input_img_name', [])
    artifact_parts = [Part(text="以下用户输入的图片素材：\n")]
    for i, art_name in enumerate(input_img_name):
        artifact_parts.append(Part(text=f"这是第{i + 1}张素材图片，它的名称是{art_name}，它的内容是："))
        art_part = await callback_context.load_artifact(filename=art_name)
        artifact_parts.append(art_part)
    llm_request.contents.append(Content(role='user', parts=artifact_parts))

    pgbr_image_generation_results = callback_context.state.get('pgbr_image_generation_results', {})
    logger.info(current_parameters)
    logger.info(pgbr_image_generation_results)

    image_list = None
    if 'output_artifacts' in pgbr_image_generation_results:
        image_list = pgbr_image_generation_results['output_artifacts']

    if image_list is not None and isinstance(image_list, list) and  len(image_list) > 0:
        for i, image_info in enumerate(image_list):
            logger.info(image_info)
            artifact_name = image_info['name']
            placeholder_name = image_info['placeholder_name']
            description = image_info['description']

            artifact_parts = [Part(text=f"生成的图像素材{i}的名字为:{artifact_name}，在代码中占位符的名字为{placeholder_name}，对应的描述信息为{description}。")]
            #     continue
            # artifact_parts.append(art_part)
            # logger.info(art_part)
            llm_request.contents.append(Content(role='user', parts=artifact_parts))

            #     continue
            # artifact_parts.append(art_part)
            # # logger.info(art_part)
            # llm_request.contents.append(Content(role='user', parts=artifact_parts))

    quality_analysis_results = callback_context.state.get('page_generation_by_reference/quality_analysis_results', '')
    logger.info(f"quality_analysis_results: {draft_results}")
    if len(quality_analysis_results) > 0:
        input_text = f"上一个版本的海报的质量方面的评价和修改意见为：{quality_analysis_results}\n"
        llm_request.contents.append(Content(role='user', parts=[Part(text=input_text)]))

    html_final_results = callback_context.state.get('page_generation_by_reference/final_results', '')
    logger.info(f"html_final_results: {html_final_results}")
    if len(html_final_results) > 0:
        input_text = f"上一个版本的海报的html代码为：{html_final_results}\n"
        llm_request.contents.append(Content(role='user', parts=[Part(text=input_text)]))

    return


class PGBRFinalizeAgent(BaseAgent):
    model_config = {"arbitrary_types_allowed": True}
    llm: LlmAgent

    def __init__(self, name: str, description: str = '', llm_model: str = ''):
        if not llm_model:
            llm_model = SYS_CONFIG.llm_model
        logger.info(f"PGBRFinalizeAgent: using llm: {llm_model}")

        llm_model, llm_config = build_model_and_config(llm_model)
        # now = datetime.datetime.now()
        # time_stamp = now.strftime("%Y-%m-%d")
        time_str = datetime.date.today().strftime("%Y-%m-%d")
        llm = LlmAgent(
            name=name,
            model=llm_model,
            generate_content_config=llm_config,
            description=description,
            include_contents='none',
            instruction=pgbr_finalize_instruction.format(TIME_STAMP_STR=time_str),
            before_model_callback=pgbr_finalize_before_model_callback,
            output_key = "page_generation_by_reference/final_results"
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
        now = datetime.datetime.now()
        time_stamp = now.strftime("%Y-%m-%d %H:%M:%S")
        if len(text_list) == 0:
            message = f"PGBRFinalizeAgent 生成回复失败"
            message_for_user = "生成回复失败"
            logger.error(message)
            current_output = {"author": self.name, 'status': 'error', 'message': message,
                              'message_for_user': message_for_user,
                              'output_text':'', 'time_stamp': time_stamp}
        else:
            message = f"PGBRFinalizeAgent 已完成分析和代码草稿"
            message_for_user = "已完成分析和代码草稿"
            output_text = '\n'.join(text_list)
            current_output = {"author": self.name, 'status': 'success', 'message': message,
                              'message_for_user': message_for_user,
                              'output_text': output_text, 'time_stamp': time_stamp}

        yield Event(
            author='PGBRFinalizeAgent',
            content=Content(role='model', parts=[Part(text=message)]),
            actions=EventActions(state_delta={'current_output': current_output})
        )


pgbr_finalize_instruction = '''
# 角色
你和其他agent合作来完成复现 根据用户提供的 **单张网页截图**，生成视觉上与原图**像素级高度相似且美观 (Pixel-Perfect)** 的完整前端代码的任务。
其他agent生成了代码的草稿（图像资源部分用占位符表示）、图像生成智能体生成的图像（有图像名字与图像占位符的映射关系）。
你负责根据生成的图像的名字和基本信息，来修改代码的草稿，使得它视觉上的效果和给定的截图一致，并且需要美观。
你生成的 HTML 代码可能会直接返回给用户使用，也可能用 playwright 将代码转换成图像给用户看。

# 目标
 - 保证可以运行：调整代码，尤其是文件名部分，确保代码中的文件名和给定的素材相符。
 - 满足用户的需求
 - 保持和参考图像视觉上相似，尤其是布局、整体风格。
 - 保持美观。如果有来自视觉质量专家智能体的修改意见，你需要听取这些意见并针对上一个版本的代码做修改。整体上美观优先，你可以稍微修改布局、页面大小等方面。
 


---

# 技术栈与严格约束 (Technical & Strict Constraints)

* **HTML/CSS 标准:**
    * 必须严格使用 **HTML5** 和 **CSS3**。
    * 布局必须使用 **Flexbox** 或 **CSS Grid**，以实现现代、高效的布局结构。
    * **禁止使用**任何 CSS 预处理器（如 Sass, Less）。
* **框架限制:**
    * **绝对禁止**使用任何第三方 CSS 框架（如 Bootstrap, Tailwind CSS, Bulma）。
    * **绝对禁止**使用任何 JavaScript 框架或库（如 React, Vue, jQuery）。
* **JavaScript 使用规则:**
    * **禁止使用 JavaScript**，除非截图元素绝对需要最基础的交互（例如，一个非常简单的、无状态的 Tab 切换），且代码必须是**最小化**的原生 JS。所有静态内容和样式必须在 HTML/CSS 中完成。
* **代码质量:**
    * 代码必须具备良好的语义化，清晰的注释和易读的结构。
    * 必须考虑**基本的响应式设计**，特别是针对布局的适应性。

---

# 视觉相似性与细节优先级 (Visual Priority & Detail)

你的代码必须在以下所有细节上与截图**完全一致**：

1.  **布局与间距 (Layout & Spacing):** 严格还原所有元素的 $margin$、$padding$ 和 $gap$ 值。
2.  **字体 (Typography):** 准确匹配 $font-family$、$font-size$、$font-weight$、$line-height$ 和颜色。
3.  **颜色 (Color):** 准确提取所有文本、背景、边框、阴影的颜色值（优先使用 HEX 或 RGB）。
4.  **元素位置 (Positioning):** 元素必须处于截图上的确切位置。
5.  **边框与阴影 (Borders & Shadows):** 精确还原 $border-radius$、$box-shadow$ 等样式。

---

# 图像素材处理与占位符规范 (Image Handling & Placeholders)

在把图像素材加到代码中的时候，需要注意以下的事项：
 - 注意图像的尺寸，防止最终页面上显示的尺寸不符合预期
 - 所有生成的图像素材路径都在当前文件夹
 - 你需要修改代码中的文件名，也就是把占位符修改成真实的文件名。图像文件由于已经落地存储，不能修改名字，所以你需要修改代码里面的文件名。真实的文件名是含有 'pgbr_image_generation_output' 字符串的，你一定需要将代码中文件名改成这种的。
 
# 必要信息
 - 当前时间：{TIME_STAMP_STR}
 
# 设计要求

基于上述规范和用户需求，以及可能的修改意见，你需要确保:
1. 所有元素都有明确的位置、尺寸和层级
2. 文字内容符合用户原始的要求，文本内容清晰可读，文字不可以太小。
3. 图像描述详细准确
4. 整体布局平衡美观
5. 符合海报的主题和风格定位

## 设计方法
 - 需要考虑参考图像以及设计元素分析中体现的整体设计效果，设计生成的图像需要在整体和用户心目中的结果（参考图像+任务描述中体现的）一致。具体的需要在图像主体区域、文字信息区域的比例一致。如果图像和文字有改动，你需要想办法来尽量保持比例一致
 - 在整体满足用户心目中图像的要求之后，考虑细节部分，各个图像区域，各个文字区域，需要精细调整位置、大小、相对尺寸比例，使得整体效果美观。不要出现文字过小看不清，装饰性元素过大导致主体不突出，颜色搭配不合理等等问题。

 
# 其他要求
 - 在网页下方加上 "By naicha.ai" 的字样作为标志。
 - 注意遮挡和层次关系，需要和参考图像一致。比如图像是否可以遮挡文字，文字是否可以遮挡图像。如果代码草稿里面的不符合要求，你需要修改一下。
 - 你可以稍微调整代码，使得最终效果美观。
 - 不要使用印章效果。

---

# 输出格式要求 (Required Output Format)

你的输出必须是一个遵循以下 JSON 结构的单一对象。不需要有解释性质的文字。json之外不要有其他文字。

| 字段名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `pgbr_html_code_final` | 字符串 | 包含完整的 **HTML (含 `<style>...</style>` 或外部 CSS 引用)** 代码。|
| `pgbr_image_name_list` | list，元素为字符串 | 包含 pgbr_html_code_final 中需要全部的图像的真实文件名，需要与代码中的文件名一致，一定含有 'pgbr_image_generation_output' 字符串。|
| 'suggested_width'| int | 生成的这个网页在用playwright 转换成图片的时候，最佳 viewport 的width，可选项。不填的话系统默认为1024 | 
| 'suggested_height'|int |  生成的这个网页在用playwright 转换成图片的时候，最佳 viewport 的height，可选项。不填的话系统默认为768 | 
| 'time_stamp'| string |  当前步骤的时间戳，格式为"%Y-%m-%d %H:%M:%S"，可以从`当前步骤的 time_stamp 是：`字段获取获取。 | 
---

下面开始任务
'''

