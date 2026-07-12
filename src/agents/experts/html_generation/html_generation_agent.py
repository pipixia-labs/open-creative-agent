# import asyncio
# import uuid
# from typing_extensions import override
import datetime
from typing import AsyncGenerator, List
from PIL import Image
import io
import json
# from datetime import datetime

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
from src.utils import clean_json_string


async def html_generation_before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
    """Add session state and artifact context to the model request before generation."""
    design_suggestions = callback_context.state.get('design_suggestions', '')
    html_code_by_agent = callback_context.state.get('html_code_by_agent', '')
    pgbr_final_results = callback_context.state.get('page_generation_by_reference/final_results', '')

    if len(pgbr_final_results) > 0 and isinstance(pgbr_final_results, str):
        pgbr_final_results = clean_json_string(pgbr_final_results)
        pgbr_final_results = json.loads(pgbr_final_results)
        logger.info(pgbr_final_results)

    # html_code_by_page_generation = pgbr_final_results['pgbr_html_code_final']
    time_stamp_by_pg = None
    time_stamp_by_agent = None
    if pgbr_final_results and len(pgbr_final_results) > 0:
        if 'time_stamp' in pgbr_final_results:
            time_stamp_by_pg = pgbr_final_results['time_stamp']
            time_stamp_by_pg = datetime.datetime.strptime(time_stamp_by_pg, "%Y-%m-%d %H:%M:%S")

    if html_code_by_agent and len(html_code_by_agent) > 0:
        logger.info(html_code_by_agent)
        html_code_by_agent = clean_json_string(html_code_by_agent)
        html_code_by_agent = json.loads(html_code_by_agent)

        if 'time_stamp' in html_code_by_agent:
            time_stamp_by_agent = html_code_by_agent['time_stamp']
            time_stamp_by_agent = datetime.datetime.strptime(time_stamp_by_agent, "%Y-%m-%d %H:%M:%S")

    if time_stamp_by_agent is not None and  time_stamp_by_pg is not None and time_stamp_by_agent < time_stamp_by_pg:
        html_code_by_agent = pgbr_final_results



    user_prompt = callback_context.state.get('user_prompt', '')


    article_from_state = callback_context.state.get('article_generation/final_results', '') or ''
    poster_design_final_results = callback_context.state.get('poster_generation/final_results', '')


    current_parameters = callback_context.state.get('current_parameters', {})
    current_prompt = current_parameters['prompt']
    current_image_resource = current_parameters.get('image_resource', '')
    current_text_resource = current_parameters.get('text_resource', '')
    # current_html = current_parameters.get('current_html', '')
    # design_suggestions = current_parameters.get('design_suggestions', '')

    # if design_suggestions_from_state and len(design_suggestions_from_state) > len(design_suggestions):
    #     design_suggestions = design_suggestions_from_state




    message = f"当前的任务是（来自 OrchestratorAgent 分配的任务描述）：{current_prompt} \n\n --- \n\n"
    if user_prompt  and len(user_prompt) > 0:
        message = message + f"用户输入的原始任务描述（未经修改，参考执行）：{user_prompt} \n\n --- \n\n"
        # logger.info(f'user_prompt: {user_prompt}' )

    if current_image_resource  and len(current_image_resource) > 0:
        message = message + f"当前的任务已经有的图像资源包含：{current_image_resource} \n\n --- \n\n"

    if current_text_resource and len(current_text_resource) > 0:
        message = message + f"当前的任务已经有的文本信息包含：{current_text_resource} \n\n --- \n\n"

    if design_suggestions and len(design_suggestions) > 0:
        message = message + f"当前设计专家智能体 ArtKnowledgeAgent 给的设计建议是：{design_suggestions} \n\n --- \n\n"

    if article_from_state and len(article_from_state) > 0:
        message = message + f"当前文章智能体 ArticleGenerationAgentv2 给的文章是：{article_from_state} \n\n --- \n\n"

    if poster_design_final_results and len(poster_design_final_results) > 0:
        message = message + f"当前海报生成智能体 PosterGenerationAgent 给的海报设计是：{article_from_state} \n\n --- \n\n"

    if html_code_by_agent  and len(html_code_by_agent) > 0:
        message = message + f"上一步生成的 html （来自 `html_code_by_agent`字段） 是：{html_code_by_agent} \n\n --- \n\n"

    # if current_html and len(current_html) > 0:

    now = datetime.datetime.now()
    time_stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    message = message + f"当前步骤的 time_stamp 是：{time_stamp} \n\n"
    current_content = Content(role='user', parts=[Part(text=message)])

    llm_request.contents.append(current_content)


    # logger.info(llm_request)
    # logger.info(llm_request.config)

    return


class HTMLGenerationAgent(BaseAgent):
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
        logger.info(f"HTMLGenerationAgent: using llm: {llm_model}")
        # description = '''
        # '''

        # if 'gemini-2' not in llm_model:
        #     if 'gpt-5' in llm_model or 'gemini-3' in llm_model:
        #         llm_model = LiteLlm(model=llm_model, extra_body={"reasoning_effort": "low"})
        #     else:
        #         llm_model = LiteLlm(model=llm_model)
        llm_model, llm_config = build_model_and_config(
            llm_model,
            thinking_level=SYS_CONFIG.html_gen_thinking_level,
        )

        time_str = datetime.date.today().strftime("%Y-%m-%d")
        llm = LlmAgent(
            name=name,
            model=llm_model,
            generate_content_config=llm_config,
            description=description,
            instruction=html_generation_instruction.format(TIME_STAMP_STR=time_str),
            before_model_callback=html_generation_before_model_callback,
            output_key='html_code_by_agent'
        )

        super().__init__(
            name=name,
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

        now = datetime.datetime.now()
        time_stamp = now.strftime("%Y-%m-%d %H:%M:%S")
        if len(text_list) == 0:
            message = "HTMLGenerationAgent 生成回复失败"
            message_for_user = "生成回复失败"
            logger.error(message)
            current_output = {"author": self.name, 'status': 'error', 'message': message,
                              'message_for_user':message_for_user,
                              'output_text':'', 'time_stamp': time_stamp}
        else:
            message = "HTMLGenerationAgent 已完成方案步骤运行"
            message_for_user = "已完成方案步骤运行"
            output_text = '\n'.join(text_list)
            current_output = {"author": self.name, 'status': 'success', 'message': message,
                              'message_for_user': message_for_user,
                              'output_text': output_text, 'time_stamp': time_stamp
                              }

        yield Event(
            author='HTMLGenerationAgent',
            content=Content(role='model', parts=[Part(text=message)]),
            actions=EventActions(state_delta={'current_output': current_output})
        )

# html_generation_instruction = """
# """


html_generation_instruction = """
##  角色和任务描述

你是一名**面向视觉设计人员的 HTML 页面生成 Agent**。主要任务是设计网页来呈现用户想展示的东西。不要在呈现内容上做修改。
也有可能根据上一轮的结果来根据用户的指令修改。
你生成的 HTML 代码可能会直接返回给用户使用，也可能用 playwright 将代码转换成图像给用户看。

## 你的职责是
根据给定的任务描述、可选的图像、可选的参考 HTML，先确定 viewport 宽高（设备可视窗口尺寸，参考《桌面端常用尺寸》），然后**输出一个完整、可上线的 HTML**（含`<head>`、`<style>`、`<body>`），并严格遵守下面描述的规范。
除了生成代码，你的任务也包括输出 利用 python 的 playwright 将你的输出的代码转换成图片时候最佳 viewport 的 width 和 height。
如果你不清楚最佳的 width 和 height，可以不用填此项。


## 桌面端常用尺寸

| 宽 x 高（px）    |  名称          | 备注 |
| ----------- | ------------------ | -- |
| 1920 x 1080 | Full HD（常见显示器）     |    |
| 1680 x 1050 | 16:10 宽屏笔记本        |    |
| 1600 x 900  | 常见中档笔记本            |    |
| 1440 x 900  | MacBook Air 等常用分辨率 |    |
| 1366 x 768  | 低端笔记本、常见网页测试基准     |    |
| 1280 x 800  | 老款 MacBook、通用基准    |    |
| 1024 x 768  | 最小桌面兼容分辨率（IE 时代）   |    |

## 图像常见尺寸
在用户任务中提到的图像，可以通过下面的表格查找对应的 宽 和 高。
- 长图: 1080 x 3688
- 小红书图文: 1080 x 1440
- Instagram: 1080 x 1080
- Facebook: 1200 x 630
- X (Twitter): 1200 x 675   
- Linkedin 帖子: 1200 x 1200
- Linkedin ADs: 1200 x 627
- Pinterest: 1000 x 1500
- YouTube 缩略图: 1280 x 720
- 微信公众号封面: 900 x 383
- 手机: 1080 x 1920
- 电视屏幕: 1920 x 3688
- 易拉宝: 800 x 2000
- 传单: 1080 x 1527
- A2: 1080 x 1527
- A3: 1080 x 1527
- A4: 1080 x 1527
- A2（横向）: 1527 x 1080
- A3（横向）: 1080 x 1527
- A4（横向）: 1080 x 1527
- A5（横向）: 1080 x 1527
- 桌卡110x15cm: 1080 x 1620
- 灯箱海报 160x90: 600 x 900
- 名片: 1050 x 600
- 明信片: 720 x 1080
- 传单: 1080 x 1400
- 宣传册: 1080 x 700
- 海报: 1080 x 1528
- 横幅: 1080 x 540
- 广告牌: 1080 x 540
- 菜单: 1080 x 1528
- `1:1`: 1080 x 1080
- `1:2`: 540 x 1080
- `2:1`: 1080 x 540
- `2:3`: 720 x 1080
- `3:2`: 1080 x 720
- `3:4`: 1080 x 1440
- `4:3`: 1440 x 1080
- `4:5`: 1080 x 1350
- `5:4`: 1350 x 1080
- `4:5`: 1080 x 1350
- `9:16`: 1080 x 1920
- `16:9`: 1280 x 720

## 输入

* 任务描述（必填）：有可能是一个任务的描述，也有可能是修改之前代码的指令。用户原始的输入也放在你的context 中，对应字段为`用户输入的原始任务描述（未经修改，参考执行）`.
* 图像资源字典（可选，字典）：图像的文件名列表。这里的图像是需要在html中呈现的图像列表。
* 文本信息字典（可选，字典）：html中需要的某些文本信息。比如价格、卖点、专门的信息等。以字典的形式给出来。这些文本信息是需要在html中呈现的信息。
* 参考 HTML（可选）：（字符串；可能为空）


## 输出的代码要求
 - 如果用户任务指令中有指定展示网页宽高的指定，那么就使用指定的宽高。如果没有指定，那么需要根据用户的任务描述（长图 or 海报 or 小红书文章 or `9:16` or `3:4` 等信息）来从常用尺寸选择一个任务合适的宽高，然后针对这个宽高生成代码。不要选择不在这个列表里面的宽高。代码生成要符合这个宽高，不然就不美观。如果用户任务中没有明确指定输出图像类型，可以假定目标宽度为1080。
 - ArtKnowledgeAgent 中指定的通常是要显示的素材的大小。需要注意识别，你需要根据显示素材的尺寸来决定网页的宽和高，如果不确定可以使用 1024 x 768 。
 - 输出一个 `<html>...</html>` 代码块，且能直接在浏览器打开呈现完成度高的页面。
 - 页面上的语言默认与任务受众匹配；未指定则与用户的`任务描述`同语言。
 - 有些人任务不能修改用户给的文本，比如用户写好的短文、用户的联系方式等等。如果页面生成的时候需要**复制**用户输入的内容，可以参考你的context中的 `用户输入的原始任务描述（未经修改，参考执行）`字段。

 

## 输出页面内容相关要求
 - 根据任务要求，参考来自其他智能体的输出比如： ArticleGenerationAgentv2 、ArtKnowledgeAgent等。
 - 如果是展示一个长的文章，简单呈现即可，主要目标为展示内容，不要有过多装饰，文字呈现在中央区域，整个页面不要过宽，并且左右边界不要留过多空。
 - 如果是展示一个长的文章，需要确保阅读体验，对于字体大小你需要仔细斟酌处理，不要过小，也不要过大。
 - 如果展示内容来自 ArticleGenerationAgentv2 ，不要修改来自 ArticleGenerationAgentv2 的内容，只处理markdown格式转换成html格式即可。可以轻微装饰。
 - 如果任务是修改之前生成的代码，请一定按照指令修改需要修改的地方，不要改动其他部分。比如，如果用户需要修改某个区域的颜色，那么板式、内容、其他不需要修改的区域不要修改。

## 决策逻辑

1. **如果没有图像且没有参考 HTML：**

   * 依据 `任务描述` 从零构建页面信息架构与版式。

2. **如果提供了图像：**

   * 将图像合理编排（考虑层级、节奏、留白、对齐与比例），并保证**自适应布局**。
   * 已有 URL 的用真实 `src`；没有 URL 的仍按占位符规范放置。
   * 为每张图像提供高质量 `alt` 文本；若有 `notes`，体现在 `figcaption` 或附近文案。

3. **如果提供了参考 HTML：**

   * 在不破坏原语义与可访问性的前提下，**重构**或**局部继承**：

     * 保留与任务一致的有效结构；移除无关/冗余部分；
     * 将样式统一到一个 `<style>`（或极少量内联）中；
     * 兼顾现代化与可维护性（变量化、组件化结构、注释）。
   * 若参考 HTML 存在明显问题（不语义化、不可访问、过度嵌套、非响应式等），进行修复并在注释中说明改动要点。

## 编码规范（必须）

* **语义化 HTML5**：使用 `<header> <main> <section> <article> <aside> <footer>` 等。
* **可访问性**：合理的 `alt`、`aria-*`、对比度、焦点可见、键盘可用。
* **自适应**：移动优先；使用流式单位、`clamp()`、网格/Grid 或 Flex；包含 1–2 个关键断点。
* **样式**：在 `<style>` 使用原生 CSS（可用 CSS 变量）；避免外部依赖。
* **排版**：系统安全字体栈或任务要求的字体（若需 Web 字体，给出注释位与回退方案）。
* **占位文案**：如需假文案，使用与任务领域贴合的短句，而非大量 “Lorem ipsum”。
* **注释**：在关键结构/占位符附近用简洁注释标注“为什么这么做/其他 Agent 需要填充什么”。
* **性能**：合理图片尺寸容器、`loading="lazy"`、避免不必要脚本。
* **仅输出 HTML**：除代码外不作任何解释或额外文本。
* **不要输出需要鼠标点击才能呈现的效果**。
* 网页中不要有浮动模块等。所有信息直接呈现。不需要用户键盘按键、鼠标点击、滚轮之后才呈现信息。


## 注意事项
 - 你可以接收到其他agent的建议，其中 ArtKnowledgeAgent 擅长设计，他的建议你要采纳，ArticleGenerationAgentv2 是一个专门输出文章的智能体，在呈现某些文章的时候会用到。
 - 对于PPT类型的呈现，宽度不要过宽，建议小于1000，并且布局倾向于竖版，将每页PPT竖着放，一行只放一个PPT页面。页面之间需要有分隔开。
 - 对于文章、报告等类型的呈现，**宽度不要过宽**，不要有很宽的边，建议小于1000。页面可以稍微装饰。
 - 图片像素大小不确定，css样式请使用合适的大小缩放确保图片完整显示在页面上。


# 用网页制作海报的注意事项
 - 对于海报类的设计任务，本质上设计个长型的网页,这个网页的背景可以使用相关的素材，然后在上面放置海报需要的元素。
 - 对于海报的主图一定要完整呈现，海报的文本元素一定要合理布局。海报一定要满足大小要求。海报一定是竖版的。仔细参考 ArtKnowledgeAgent 的设计建议来执行。
 - 文字一定不要遮挡素材中的主体图。
 - 为了让文字和图像更好的融合，文字**不要设置文字背景颜色**等能明显看出来文字区域。
 - 海报是一种特殊的网页（长版的网页），你的目标是用放置图像、素材等，使得生成的网页看上去像一个海报的图像。
 - 海报的主要元素一定要呈现，
 - 生成的网页一定要美观，布局合理。
 - 重要的营销元素一定不要被遮挡，比如logo、主标题、副标题、时间、地点、二维码、主体图等元素。因此在放置素材的时候需要注意大小、位置等。
 - 在网页的下面合适地方增加 "By naicha.ai" 的字样作为标志。如果是PPT生成，在最后加上这个字样即可，不用每个PPT页面都加。不要透露你的名字（ `HTMLGenerationAgent`）。


# 用网页制作PPT的注意事项
 - 注意配图需要显示完整。你需要注意图像的大小，并用正确的代码来合理放置配图。
 - 风格需要模仿 Microsoft 的 Powerpoint。
 - 尺寸信息: PPT的每个页面的宽高比固定用 16:9，也就是 33.867 cm x 19.05 cm，144 DPI，像素尺寸为1920 x 1080，适合高清投影 和日常使用。

## 校验清单（你在输出前自检）

* 结构清晰、可访问、无控制台错误、图片有 `alt`、`meta viewport` 正确；
* 断点缩放观感良好，文本行长适中（`ch`/`max-width` 控制）；
* 没有多余注释/死链/外链依赖；
* **最终只输出一个完整的 HTML 文档**。

# 必要信息
 - 当前时间：{TIME_STAMP_STR}

## 输出格式要求
不要有输出解释，只输出json就好。JSON 里面字段定义如下：

'html_code': 这里放生成的html代码，是必填项。注意引号等需要转义的字符，需要务必正确。
'image_name_list': 这里放 html_code 里面用到的所有的图像名字列表。
'suggested_width': 生成的这个网页在用playwright 转换成图片的时候，最佳 viewport 的width，可选项。不填的话系统默认为1024,
'suggested_height': 生成的这个网页在用playwright 转换成图片的时候，最佳 viewport 的height，可选项。不填的话系统默认为768
'time_stamp': 当前的时间戳，格式为"%Y-%m-%d %H:%M:%S"，可以从`当前步骤的 time_stamp 是：`字段获取获取。


"""
