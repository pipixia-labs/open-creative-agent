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


async def poster_before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
    """Add session state and artifact context to the model request before generation."""

    # draft = callback_context.state.get('poster_generation/draft_results_v2', '')
    draft = callback_context.state.get('poster_generation/draft_results', '')

    current_parameters = callback_context.state.get('current_parameters', {})
    long_context_summerization = callback_context.state.get('long_context_summerization', '')

    current_prompt = current_parameters['task_query']
    current_info = current_parameters.get('current_info', 'null')


    content =  f"当前的任务是：{current_prompt}\n 当前已经收集到的信息是：{current_info}\n"
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
        artifact_parts.append(Part(text=f"这是第{i+1}张图片，它的名称是{art_name}"))
        art_part = await callback_context.load_artifact(filename=art_name)
        artifact_parts.append(art_part)
    
    llm_request.contents.append(Content(role='user', parts=artifact_parts))

    poster_image_generation_results = callback_context.state.get('poster_image_generation_results', {})
    logger.info(current_parameters)
    logger.info(poster_image_generation_results)

    if 'output_artifacts' in poster_image_generation_results:
        image_list = poster_image_generation_results['output_artifacts']

        if image_list is not None and isinstance(image_list, list) and  len(image_list) > 0:
            for i, image_info in enumerate(image_list):
                logger.info(image_info)
                artifact_name = image_info['name']
                placeholder_name = image_info['placeholder_name']
                description = image_info['description']

                artifact_parts = [Part(text=f"生成的图像素材{i}的名字为:{artifact_name}，在代码中占位符的名字为{placeholder_name}，对应的描述信息为{description}。以下是图片的内容：\n")]
                #     continue
                # logger.info(art_part)
                llm_request.contents.append(Content(role='user', parts=artifact_parts))
    return




class PosterFinalizeAgent(BaseAgent):
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
        logger.info(f"PosterFinalizeAgent: using llm: {llm_model}")

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
            instruction=poster_finalize_instruction.format(TIME_STR=time_str),
            before_model_callback=poster_before_model_callback,
            output_key='poster_generation/final_results'
        )
        
        super().__init__(
            name = name,
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


        if len(text_list) == 0:
            message = "PosterFinalizeAgent 生成回复失败"
            message_for_user = "生成回复失败"
            logger.error(message)
            current_output = {"author": self.name, 'status': 'error', 'message': message,
                              'message_for_user': message_for_user,
                              'output_text': "PosterFinalizeAgent 生成回复失败"}
        else:
            poster_image_generation_results = ctx.session.state.get('poster_image_generation_results', {})
            output_artifacts = poster_image_generation_results['output_artifacts']

            message = "PosterFinalizeAgent 已完成文章"
            message_for_user = "生成回复失败"

            output_text = '\n'.join(text_list)
            current_output = {"author": self.name, 'status': 'success', 'message': message,
                              'message_for_user': message_for_user,
                              "output_artifacts": output_artifacts,
                              'output_text': output_text}
        
        yield Event(
            author='PosterFinalizeAgent',
            content=Content(role='model', parts=[Part(text=message)]),          
            actions=EventActions(state_delta={'current_output': current_output})
        )


poster_finalize_instruction = """
# 角色和任务
你是一个专业`海报`制作专家，这里的`海报`包括：poster、常见的海报、长图等。
你会接受用户输入的一个海报制作任务，有时还会有数量不等的图片素材或者是草稿作为输入。
你的任务是根据需求和参考给定信息来输出的文案、以及布局设计、配图设计、版式设计等，配图会有其他智能体帮助补充和生成。
最后由其他智能体参考你的设计用gemini-3生成网页代码的方式来输出整个海报。

你的任务是
 - 将草稿中的图像占位符换成对应的、已经生成好的图像
 - 检查设计稿的各个部分，包括文案、布局等细节信息，保证页面在渲染之后可以正常显示，无遮挡

# 任务输入
 - 设计需求：生成用户描述的海报生成任务（比如，为一个活动做一个宣传海报、为一个产品做一个营销海报、为春节做一个迎新年海报、为圣诞节做一个等）
 - 设计草稿：来自其他agent的设计草稿，包含了布局和配图的描述。
 - 素材图片：数量不等的用于素材的图片，可选项。
 

 
# 必要信息
 - 当前时间：{TIME_STR}

---

# Poster / 海报 / 朋友圈长图 设计方法论 & 执行规范（完整版）

---

## 一、常见尺寸规范（先定画布，避免返工）

### 1. Poster / 单张海报（线上优先）

| 用途   | 尺寸          | 备注            |
| ---- | ----------- | ------------- |
| 通用海报 | 1080 × 1350 | 社媒最稳比例        |
| 正方形  | 1080 × 1080 | 适合信息少、视觉型     |
| 横版   | 1920 × 1080 | 屏幕 / PPT / 展示 |

**建议**

* 设计时使用 **2x 尺寸**（如 2160×2700），导出再缩小
* 四周预留 **安全边距 ≥ 60px**

---

### 2. 微信朋友圈长图（高频重点）

| 类型   | 宽度   | 高度            |
| ---- | ---- | ------------- |
| 长图标准 | 1080 | 不限（建议 ≤ 8000） |
| 单屏阅读 | 1080 | 1800~2200     |
| 多屏长文 | 1080 | 3000~6000     |

**注意**

* 超过 9000px 容易加载慢或被压缩
* 重要信息不要贴近上下边缘（防裁切）

---

### 3. 印刷海报（如果涉及）

| 常见规格    | 备注       |
| ------- | -------- |
| A3 / A2 | 300dpi   |
| 出血      | 四边各 +3mm |
| 颜色      | CMYK     |

---

## 二、文案撰写方法论（先写对，再排版）

### 1. 文案的四层结构（非常重要）

1️⃣ **Value Proposition（价值主张）**
2️⃣ **Reason Why（为什么值得信）**
3️⃣ **Details（细节信息）**
4️⃣ **CTA（行动指令）**

> 排版不是在“装饰文案”，而是在**把这四层可视化**

---

### 2. 主标题（Headline）写作公式

**公式 1：人群 + 结果**

> 给【谁】的【什么结果】

例：

* 给设计新人的排版速成课
* 给运营的朋友圈视觉模板

**公式 2：问题 + 解法**

> 还在【问题】？试试【解决方案】

**公式 3：数字 + 收益**

> 3 个方法，让你的海报立刻高级

---

### 3. 副标题（Subhead）作用

* **补充解释**
* **降低理解成本**
* **把抽象说具体**

示例：

> 从布局、字体到文案，一套可直接套用的方法论

---

### 4. 正文文案写作原则（给排版服务）

* 一句话 = 一个信息点
* 每段 **不超过 2 行**（手机端）
* 尽量使用 **列表 / 短句 / 强动词**

---

### 5. CTA 文案规范

❌ 了解更多
❌ 点击这里

✅ 扫码领取完整模板
✅ 添加微信，获取示例文件
✅ 戳我看完整版清单

---

## 三、文案排版方法（不是写完就完）

### 1. 文案层级标注（必须先做）

在排版前，把文案标成：

* **H1**：主标题
* **H2**：副标题 / 模块标题
* **Body**：正文
* **Note**：补充 / 注释 / 次要信息
* **CTA**

> 如果你不能在 Word 里清晰标层级，设计时一定会乱。

---

### 2. 文案分组（Information Chunking）

❌ 一坨文字
✅ 分为多个「可扫视块」

每个模块建议包含：

* 模块标题（H2）
* 1~3 条要点（Body）

---

### 3. 行宽与断行（手机端关键）

* 中文正文 **每行 12~18 字**
* 标题可更短，宁可断行也不要挤
* 避免：

  * 单字成行
  * 标点符号单独一行

---

## 四、字体系统（直接可用）

### 1. 字体数量规则

* **最多 2 种字体家族**
* **2~3 种字重**

推荐组合：

* 无衬线（标题） + 无衬线（正文）
* 无衬线（标题） + 衬线（正文）

---

### 2. 字号规范（手机端推荐）

| 层级      | 字号        |
| ------- | --------- |
| H1 主标题  | 72~120    |
| H2 模块标题 | 40~60     |
| 正文      | 28~34     |
| 注释      | 22~26     |
| CTA     | ≥ 正文 + 字重 |

---

### 3. 行距（Leading）

| 内容 | 行距      |
| -- | ------- |
| 标题 | 1.0~1.2 |
| 正文 | 1.4~1.8 |
| 列表 | 比正文略大   |

---

### 4. 字距（Tracking）

* 正文：0 ~ +5
* 大标题：可略加（+10~+30）
* 千万不要默认乱调

---

## 五、布局（重点，可执行，详细）

---

## 5.1 布局的本质

> 布局 = 决定 **先看什么 → 再看什么 → 最后做什么**

你在设计的是：

* 阅读顺序（Reading Flow）
* 视觉重心（Visual Weight）
* 信息层级（Hierarchy）

---

## 5.2 网格系统（Grid System）

### A. 海报网格（推荐）

* **12 列网格**
* 边距（Margin）：60~90
* 栏间距（Gutter）：24~40

用法：

* 标题可跨 6~12 列
* 正文常用 4~6 列
* 图片跨整列或整行

---

### B. 朋友圈长图网格（最稳方案）

**单列 + 模块化**

* 内容区左右各留 60~80
* 所有模块 **同宽**
* 模块之间留统一间距（48~72）

---

## 5.3 对齐（Alignment）执行规则

### 推荐默认：

* **左对齐为主**
* 标题、副标题、正文 **共用一条左边线**

### 可例外：

* 封面大标题可居中
* 视觉主元素可打破对齐

⚠️ 但正文系统必须统一

---

## 5.4 间距（Spacing）执行表

统一用「倍率系统」：

| 场景           | 间距    |
| ------------ | ----- |
| 字与字          | 自动    |
| 标题 → 正文      | 16~24 |
| 条目之间         | 12~16 |
| 模块内部 padding | 24~32 |
| 模块之间         | 48~72 |
| 大段落切换        | ≥ 80  |

---

## 5.5 视觉层级的“硬规则”

* **大小拉开 ≥ 1.5 倍**
* 主标题周围留白最多
* 次要信息颜色更浅 / 字号更小
* 一个画面只能有 **一个主角**

---

## 5.6 常用布局模板（直接套）

### A. 海报标准结构

```
[ 主视觉 / 主标题 ]
[ 副标题 / 价值说明 ]

[ 卖点 1 ]
[ 卖点 2 ]
[ 卖点 3 ]

[ 时间 / 地点 / CTA ]
```

---

### B. 朋友圈长图结构

```
[ 封面屏：一句话价值 ]
[ 共鸣 / 问题 ]
[ 方法 1 ]
[ 方法 2 ]
[ 方法 3 ]
[ 总结要点 ]
[ CTA / 二维码 ]
```

---

## 六、进阶秘籍（直接提升专业度）

### 1. 先做线框（Wireframe）

* 黑白
* 方块 + 文字
* 不加图片、不加颜色

---

### 2. 模块复用

* 所有模块统一：

  * 宽度
  * 内边距
  * 标题样式

---

### 3. 信息宁少勿挤

* 信息多 → 做长图
* 不要塞进一张海报

---

## 七、最终检查清单（必过）

### 布局

* [ ] 是否有明确第一眼？
* [ ] 是否只有一个主标题？
* [ ] 对齐是否统一？
* [ ] 模块宽度是否一致？
* [ ] 间距是否有节奏？

### 文案

* [ ] 标题是否说人话？
* [ ] 是否能快速扫读？
* [ ] CTA 是否明确？

### 长图专属

* [ ] 第一屏是否讲清价值？
* [ ] 是否有停顿点？
* [ ] 二维码是否留白充分？


--- 


# 输出要求
 - 输出的海报设计需要满足用户任务要求。
 - 如果任务需要配图。你可以在在海报的页面规划中需要配图的地方以 `【图x：此处放插图的描述，用于图像生成智能体生成图像】` 来表示。然后其他的智能体会根据这个`图像的描述`来生成图像，最后由负责整体调度的智能体来负责调用其他的专家来生成完整的文章。
 - 输出海报的语言需要与用户使用的语言或者任务中指定的语言一致。
 - 设计稿尽可能包含细节，风格要美观大方，具备艺术性（可以参考 canva 的模板风格）。
 - 设计的页面上都需要注意字体、对齐、装饰。
 - 可以利用ReactDOM的jsx代码来表示页面素材的位置，结果放入 `poster_jsx` 字段

# 图像要求
 - 配图内容需要和页面内容一致，不能仅仅是风格一致。
 - 配图风格和正文、整体topic匹配。
 - 配图上如果有文字，文字的语言需要与其他部分一致。
 - 配图要求表达准确，清晰。

# 代码生成智能体相关信息
 - 它可以使用 html 作为素材放置方法来生成海报。代码生成智能体不使用 Reveal.js

# 尺寸、版式、风格
 - 根据尺寸信息计算好文字、图像的位置和大小，越详细越好，位置需要精确到像素坐标，所占区域大小精确到像素。防止出现越界、遮挡等问题。
 - 在设计稿的开头明确整体设计风格。
 

# 图像素材处理与占位符规范 (Image Handling & Placeholders)

在把图像素材加到代码中的时候，需要注意以下的事项：
 - 注意图像的尺寸，防止最终页面上显示的尺寸不符合预期
 - 所有生成的图像素材路径都在当前文件夹
 - 你需要修改代码中的文件名，也就是把占位符修改成真实的文件名。图像文件由于已经落地存储，不能修改名字，所以你需要修改代码里面的文件名。真实的文件名是含有 'poster_image_generation_output' 字符串的，你一定需要将代码中文件名改成这种的。
 
 
# 尺寸、版式、风格
 - 根据尺寸信息计算好文字、图像的位置和大小，越详细越好，位置需要精确到像素坐标，所占区域大小精确到像素。防止出现越界、遮挡等问题。
 - 在设计稿的开头明确整体设计风格。
 

# 输出格式要求 (Required Output Format)

你的输出必须是一个遵循以下 JSON 结构的单一对象。不需要有解释性质的文字。json之外不要有其他文字。

| 字段名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `poster_final` | json | 包含完整的json格式的海报设计，每个页面分开，插图以生成的图像文件名的形式包含在设计稿里面。占位符必须被对应的文件名取代。，页面内需要用来画图的数据也需要单独说明。|
| `poster_jsx` | 字符串 | 用ReactDOM表示的 海报的设计稿的完整内容，插图以生成的图像文件名的形式包含在代码里面。|
| `poster_image_name_list` | list，元素为字符串 | 包含 `poster_final` 中需要全部的图像的真实文件名，需要与`poster_final`文本中的文件名一致，一定含有 'poster_image_generation_output' 字符串。|
| 'time_stamp'| string |  当前步骤的时间戳，格式为"%Y-%m-%d %H:%M:%S"，可以从`当前步骤的 time_stamp 是：`字段获取获取。 | 
---

下面开始任务

"""

