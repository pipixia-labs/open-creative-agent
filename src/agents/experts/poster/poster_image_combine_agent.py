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

async def poster_image_combine_before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
    """Add session state and artifact context to the model request before generation."""

    draft = callback_context.state.get('poster_generation/draft_results', '')
    current_parameters = callback_context.state.get('current_parameters', {})
    long_context_summerization = callback_context.state.get('long_context_summerization', '')

    current_prompt = current_parameters['task_query']
    current_info = current_parameters.get('current_info', 'null')

    content = f"当前的任务是：{current_prompt}\n 当前已经收集到的信息是：{current_info}\n"
    if len(draft) > 0:
        content = content + f"当前已经有的草稿是：{draft} \n"

    if len(long_context_summerization) > 0:
        content = content + f"当前针对搜索信息提取整理之后的信息为：{long_context_summerization} \n"

    logger.info(content)
    current_content = Content(role='user', parts=[Part(text=content)])
    llm_request.contents.append(current_content)

    # if len(current_parameters.get('reference_image_name', []))==0:
    #     return

    now = datetime.datetime.now()
    time_stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    message = f"当前步骤的 time_stamp 是：{time_stamp} \n\n"
    current_content = Content(role='user', parts=[Part(text=message)])
    llm_request.contents.append(current_content)

    input_img_name = current_parameters.get('reference_image_name', [])
    artifact_parts = [Part(text="以下是你可以参考的图片：\n")]
    for i, art_name in enumerate(input_img_name):
        artifact_parts.append(Part(text=f"这是第{i + 1}张图片，它的名称是{art_name}"))
        art_part = await callback_context.load_artifact(filename=art_name)
        artifact_parts.append(art_part)

    llm_request.contents.append(Content(role='user', parts=artifact_parts))
    return


class PosterImageCombineAgent(BaseAgent):
    model_config = {"arbitrary_types_allowed": True}
    llm: LlmAgent

    def __init__(
            self,
            name: str,
            description: str = '',
            llm_model: str = ''
    ):
        if not llm_model:
            llm_model = SYS_CONFIG.article_llm_model
        logger.info(f"PosterImageCombineAgent: using llm: {llm_model}")

        # if 'gemini' not in llm_model:
        #     if 'gpt-5' in llm_model:
        #         llm_model = LiteLlm(model=llm_model, extra_body={"reasoning_effort": "high"})
        #     else:
        #         llm_model = LiteLlm(model=llm_model)
        llm_model, llm_config = build_model_and_config(llm_model)

        time_str = datetime.date.today().strftime("%Y-%m-%d")
        llm = LlmAgent(
            name=name,
            model=llm_model,
            generate_content_config=llm_config,
            description=description,
            # include_contents='none',
            instruction=poster_image_combine_instruction.format(TIME_STR=time_str),
            before_model_callback=poster_image_combine_before_model_callback,
            output_key='poster_generation/draft_results_v2'
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
            message = "PosterImageCombineAgent 生成回复失败"
            message_for_user = "生成回复失败"
            logger.error(message)
            current_output = {"author": self.name, 'status': 'error', 'message': message,
                              'message_for_user': message_for_user,
                              'output_text': "PosterImageCombineAgent 生成回复失败"}
        else:
            message = "PosterImageCombineAgent 已完成文章"
            message_for_user = "生成回复失败"

            output_text = '\n'.join(text_list)
            current_output = {"author": self.name, 'status': 'success', 'message': message,
                              'message_for_user': message_for_user,
                              'output_text': output_text}

        yield Event(
            author='PosterImageCombineAgent',
            content=Content(role='model', parts=[Part(text=message)]),
            actions=EventActions(state_delta={'current_output': current_output})
        )


poster_image_combine_instruction = """
# 角色和任务
你是一个专业`海报`制作专家，这里的`海报`包括：poster、常见的海报、长图等。
你会接受用户输入的一个海报制作任务，有时还会有数量不等的图片素材或者是草稿作为输入。


你的任务是
 - 根据需求、设计草稿（用json表示的文案、布局设计、配图设计、版式设计等），将草稿重新归纳总结，将所有图像以相同视觉效果表达到一张图像的prompt中。后面会使用一次文生图模型来生成一张素材图像。这个合并步骤主要是为了防止图像放置、抠图等细节问题。
 - 需要注意保持素材相对位置、排版等方面。一定同时参考设计稿里面的描述以及代码。
 - 文件名的placeholder需要修改。素材文件合并之后，设计稿所有部分都重新修正一下。使得其他智能体可以只根据这个设计搞生成配图和html代码来生成海报。你需要保证生成质量。
 - 生成的图像需要整体上和谐，不要有明显的突兀或者不符合逻辑、融合不好的地方。优先考虑美感和整体和谐，如果你觉得不必要的素材可以删掉。
 - 将你的设计稿输出。

# 任务输入
 - 设计原始需求：生成用户描述的海报生成任务（比如，为一个活动做一个宣传海报、为一个产品做一个营销海报、为春节做一个迎新年海报、为圣诞节做一个等）
 - 设计草稿：来自其他agent的设计草稿，包含了布局和配图的描述。

# 必要信息
 - 当前时间：{TIME_STR}


# 输出格式要求 (Required Output Format)

你的输出必须是一个遵循以下 JSON 结构的单一对象。不需要有解释性质的文字。json之外不要有其他文字。

| 字段名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `poster_draft` | json | 包含完整的json格式的海报页面设计，包含文案和布局，内部的插图以placeholder的形式包含在文章里面，页面内需要用来画图的数据也需要单独说明。|
| `poster_jsx` | 字符串 |  用ReactDOM表示的 设计稿的完整内容，内部的插图以placeholder的形式包含，页面内需要用来画图的数据也需要单独说明。可以认为是 `poster_draft` 的代码化表示。 |
| `poster_image_to_generate` | 数组 | 存放需要向图像生成智能体请求的**图像信息清单**。数组长度一定为1。 |


`poster_image_to_generate` 数组元素结构:

| 字段名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `description` | 字符串 | 对图像内容和风格的**详细文字描述**，用于图像生成（例如：`一张阳光明媚的咖啡馆内景图，极简主义风格`）。务必不要使用透明的图像，因为当前抠图能力不够好。 |
| `aspect_ratio` | 字符串 | 图片在代码中需要的**宽高比**（取值必须为 "1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9" 中的一个，不可以选其他值。）。 |
| `resolution` | 字符串 | 图片在代码中需要的**分辨率**（取值为`1K`, `2K`, `4K` 中的一个）。 |
| `file_name_placeholder` | 字符串 | 你在`poster_draft_v2`中使用的**占位符文件名**。 |
---

下面开始任务

"""

