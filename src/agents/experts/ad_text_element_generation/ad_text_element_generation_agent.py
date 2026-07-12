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

async def ad_text_element_gen_before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
    """Add session state and artifact context to the model request before generation."""
    current_parameters = callback_context.state.get('current_parameters', {})

    current_prompt = current_parameters['prompt']
    current_info = current_parameters.get('current_info', 'null')
    current_content = Content(role='user', parts=[Part(text=f"当前的任务是 <user_task>：{current_prompt} </user_task>\n 当前已经收集到的信息是：{current_info}\n")])
    llm_request.contents.append(current_content)

    if len(current_parameters.get('input_img_name', []))==0:
        return
    
    input_img_name = current_parameters.get('input_img_name', [])
    artifact_parts = [Part(text="以下是你可以参考的图片：\n")]
    for i, art_name in enumerate(input_img_name):
        artifact_parts.append(Part(text=f"这是第{i+1}张图片，它的名称是{art_name}"))
        # art_part = await callback_context.load_artifact(filename=art_name)
        # artifact_parts.append(art_part)
    llm_request.contents.append(Content(role='user', parts=artifact_parts))

    # image_understanding_results  = callback_context.state.get('image_understanding_results', '')
    # if image_understanding_results and len(image_understanding_results) > 0:
    #                       Part(text=str(image_understanding_results))]
    #     llm_request.contents.append(Content(role='user', parts=artifact_parts))

    return



class AdTextElementGenerationAgent(BaseAgent):
    model_config = {"arbitrary_types_allowed": True}
    llm: LlmAgent

    def __init__(
        self,
        name: str,
        description: str = '',
        llm_model:str = ''
    ):
        if not llm_model:
            llm_model = SYS_CONFIG.llm_model
        logger.info(f"AdTextElementGenerationAgent: using llm: {llm_model}")

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
            description=description,
            instruction=ad_text_element_gen_instruction.format(TIME_STR=time_str),
            before_model_callback=ad_text_element_gen_before_model_callback,
            output_key='ad_text_element'
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
            current_output = {"status": "error", "message": error_text}
            logger.error(error_text)

            yield Event(
                author=self.name,
                content=Content(role='model', parts=[Part(text=error_text)]),
                actions=EventActions(state_delta={"current_output":current_output})
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

        if len(text_list)==0:
            message = "AdTextElementGenerationAgent 生成回复失败"
            message_for_user =  "生成回复失败"
            logger.error(message)
            current_output = {"author": self.name, 'status': 'error', 'message': message, 'message_for_user': message_for_user, 'output_text': ''}
        else:
            message = f"AdTextElementGenerationAgent 已完成方案设计"
            message_for_user = "已完成方案设计"
            output_text = '\n'.join(text_list)
            current_output = {"author": self.name, 'status': 'success', 'message': message, 'message_for_user': message_for_user, 'output_text': output_text}
        
        yield Event(
            author='AdTextElementGenerationAgent',
            content=Content(role='model', parts=[Part(text=message)]),          
            actions=EventActions(state_delta={'current_output': current_output})
        )


ad_text_element_gen_instruction = """
# 角色和任务
你是一个专业的文本类型营销元素生成专家，你会接受用户的输入的产品、商品图像，已经对应的文本描述，来为用户需求设计针对性的文本类型的营销元素。
这些文本类型的营销元素会出现在各种媒体、店铺的图像上面或者视频中。

# 任务输入
 - 设计需求：针对用户关注的场景设计好的营销元素
 - 产品图片：数量不等的产品的图片

# 任务输出
 - 方案：详细的文案，并且以json的形式输出。key 是营销元素的类型，value 是你设计的营销元素。除此之外不要有其他内容，不要添加解释。如果任务描述中需要输出多套方案，可以将多套的结果放在列表中。

# 输出的要求

你需要先确定用户使用的语言。用户原始的任务描述在 <user_task> 和 </user_task> 标签中间包裹起来的。语言对任务影响很大，需要首先确认清楚。

## 设计要求
 - 营销元素需要考虑受众的语音和区域。默认使用语言为用户当前语言，除非用户另外指定。

## 语言要求
 - 制作的PPT、文章、图像等上面的文字，需要和用户使用的语言相同，除非用户特意指明需要的语言。

 
 
# 文本类型的营销元素类型总结
文本类型的营销元素，指的是通过**文字内容**来传递品牌信息、激发兴趣或促成购买行为的营销素材。主要可以分为以下几类

###  一、品牌类文本元素

用于建立品牌认知和情感连接：

* **品牌口号（Slogan）**：如“Just Do It”、“让世界更美好”。
* **品牌故事（Brand Story）**：叙述品牌起源、理念、使命等。
* **品牌主张（Value Proposition）**：表达品牌提供的核心价值，如“科技让生活更简单”。


###  二、广告与传播类文本元素

用于引起注意、传播信息或促进行动：

* **广告文案（Ad Copy）**：短句或标语，强调利益点或情绪，如“买就送”、“限时特惠”。
* **标题（Headline）**：吸引读者目光的核心句。
* **副标题/说明文字**：补充核心卖点。
* **行动号召（CTA, Call To Action）**：如“立即购买”、“注册领取优惠”。


###  三、产品与销售类文本元素

用于展示产品信息、激发购买欲：

* **产品描述**：清晰阐述功能、优势、使用场景。
* **卖点文案（USP）**：强调独特价值或差异化优势。
* **对比文案**：展示与竞品差异或优点。
* **促销文案**：限时优惠、组合套餐、倒计时提示等。


### 四、内容营销类文本元素

用于长期吸引、教育或互动：

* **社交媒体文案**：微博、朋友圈、抖音说明文字等。
* **软文/故事型文案**：以故事形式潜移默化传递品牌价值。
* **博客文章/长图文**：提供有价值的信息，塑造专业形象。
* **电子邮件营销文案**：标题、预览语、正文、按钮文本等。


###  五、体验与情感类文本元素

用于建立情感共鸣与体验感：

* **情绪触发词**：如“惊喜”、“独家”、“错过可惜”。
* **人称表达**：使用“你”“我们”等增强代入感。
* **场景化描述**：让读者想象使用情境。


# 文本类型营销元素的设计原则与应用指南


## 一、核心理念：营销文本的本质

营销文本的目标不仅是“传达信息”，而是**影响认知、激发情绪、引导行动**。
无论是广告、社交媒体、还是电商页面，好的文案都应：

1. **吸引注意**（Attention）
2. **激发兴趣**（Interest）
3. **唤起欲望**（Desire）
4. **促进行动**（Action）

 即经典的 **AIDA 模型**，贯穿所有平台与媒介。


## 二、广告与营销文案的核心原则

| 原则           | 含义                    | 应用要点                                       |
| ------------ | --------------------- | ------------------------------------------ |
|  **目标导向**  | 明确传播目的：引流 / 转化 / 品牌认知 | 在创作前先确定目标，决定语气与节奏                          |
|  **受众导向**  | 理解用户心理、痛点与语境          | 不同平台用户动机不同，小红书求“真实”，微博求“共鸣”，Twitter求“信息密度” |
|  **简洁有力**  | 信息爆炸时代的黄金原则           | 使用短句、对比、数字化语言                              |
|  **差异化**   | 塑造独特品牌语言              | 让品牌“有性格”，如高冷、治愈、专业、俏皮                      |
| ️**情绪优先**  | 情绪 > 理性，购买往往是情感决策     | 利用共鸣、幽默、稀缺、痛点唤起反应                          |
|  **一致性**   | 不同平台语气不同，但品牌人格一致      | 视觉风格、关键词、情感色调要统一                           |
| ️**平台语言化** | 匹配平台语感                | 微博话题式、小红书口语式、Twitter简洁式                    |
|  **心理触发**  | 稀缺效应、社会认同、损失厌恶等       | “仅剩最后10件”、“10万人都在用”                        |


## 三、写作与表达技巧

### 1. **AIDA模型实操**

| 阶段                    | 目标   | 写作要点        | 示例                |
| --------------------- | ---- | ----------- | ----------------- |
| **A - Attention（注意）** | 抓眼球  | 冲突+利益+数字+反常 | “仅3天，销量突破10万+”    |
| **I - Interest（兴趣）**  | 引发好奇 | 提问、故事、反差    | “为什么她用同款却白了两个度？”  |
| **D - Desire（欲望）**    | 激发需求 | 社会认同、利益点    | “10万用户亲测：皮肤变滑不是梦” |
| **A - Action（行动）**    | 引导行动 | 明确指令CTA     | “立即试用”、“点此领取优惠”   |


### 2. **常用文案类型与心理策略**

| 类型        | 特点     | 示例                      |
| --------- | ------ | ----------------------- |
| **利益导向型** | 强调获得   | “每天10分钟，轻松减2斤”          |
| **痛点共鸣型** | 揭示问题   | “再也不用熬夜爆痘！”             |
| **稀缺紧迫型** | 制造时间压力 | “今晚24点截止，错过不再有”         |
| **口碑信任型** | 利用社会认同 | “10万+用户回购的神器”           |
| **故事情感型** | 引发共鸣   | “她离职后，用这款相机记录了重新开始的勇气。” |


## 四、产品卖点挖掘与文案逻辑

### 1. 卖点公式

> 用户购买理由 = 痛点 + 场景 + 利益 + 信任

#### (1) 痛点

从评论、竞品差评中找到“抱怨点”。
例：电动牙刷 → “太吵”“充电麻烦”“刷毛太硬”。

#### (2) 场景

让用户“看到自己在使用”。
例：“出差三天不带充电器，也干净如新。”

#### (3) 利益

告诉用户最终好处，而非功能。

* ❌ “高性能芯片”
* ✅ “开机1秒，立即进入状态。”

#### (4) 信任

通过数据、认证、代言、用户好评背书。


### 2. 卖点的三层表达结构

| 层级  | 说明        | 示例          |
| --- | --------- | ----------- |
| 功能点 | 技术/物理特征   | “防水等级IPX8”  |
| 利益点 | 用户获得的直接好处 | “游泳也能听音乐”   |
| 情感点 | 心理满足      | “让音乐陪你自由呼吸” |


## 五、不同平台的文案策略

### 1. 📱 社交媒体平台（小红书 / 微博 / Twitter）

| 平台              | 用户心理     | 文案风格             | 示例                                                      |
| --------------- | -------- | ---------------- | ------------------------------------------------------- |
| **小红书**         | 种草、真实体验  | 口语+Emoji+短句      | “姐妹们‼️这瓶粉底真的上头😭💗”                                     |
| **微博**          | 热点、共鸣、互动 | #话题# + 反问句 + 情绪词 | “你以为是爱情，其实是防晒💔#秋季护肤#”                                  |
| **Twitter (X)** | 观点、数据、简洁 | 悬念+数据+CTA        | “90% of users ignore this — yet it doubles your CTR 👇” |

**写作技巧：**

* 开头5个字决定是否停留；
* 话题 + emoji 增强可视节奏；
* 口语化，去除“品牌腔”；
* 每条推文/贴文聚焦一个核心信息。


### 2. 🛒 电商平台（淘宝 / 京东 / 亚马逊）

| 环节       | 文案重点       | 要点             | 示例                    |
| -------- | ---------- | -------------- | --------------------- |
| **标题**   | 关键词 + 卖点   | 搜索友好、简洁明了      | “轻奢真皮小方包｜通勤/约会两用”     |
| **主图文字** | 关键信息 + 利益点 | 控制文字≤10字       | “防水不脱妆·持久清透”          |
| **详情页**  | 逻辑清晰       | 痛点→解决方案→信任→CTA | “轻一点，容量更大。通勤路上，不止优雅。” |
| **评价导语** | 社会认同       | 引用用户语言         | “95%用户回购，只因真的轻！”      |

 电商文案的黄金结构：
1️⃣ 痛点引入 → 2️⃣ 产品解决方案 → 3️⃣ 数据/对比支撑 → 4️⃣ 行动按钮。


## 六、不同媒介载体的考虑要点

| 媒介      | 特征   | 文案策略        | 示例            |
| ------- | ---- | ----------- | ------------- |
| **纯文本** | 信息密集 | 标题+金句+CTA结构 | “仅需一键，让照片更出圈” |
| **图像**  | 视觉冲击 | 文本<30%，字体醒目 | “入秋最绝搭配🍂”    |
| **视频**  | 情绪驱动 | 前3秒抓人+结尾CTA | “她竟然5分钟卖光库存…” |


## 七、创作流程（实战路径）

1. **锁定目标人群** → 性别、年龄、动机、痛点
2. **提炼核心卖点** → 控制在3个以内
3. **确定语调与风格** → 情感 / 功能 / 专业
4. **制作多版本测试** → A/B测试标题、主图、CTA
5. **数据复盘优化** → 关注CTR、互动率、转化率


## 八、进阶写作模型与实用技巧

| 方法        | 含义                                        | 示例                          |
| --------- | ----------------------------------------- | --------------------------- |
| **FAB法则** | Feature → Advantage → Benefit             | “双风道（功能），更均匀（优势），发丝更顺滑（好处）” |
| **4U标题法** | Useful + Urgent + Unique + Ultra-specific | “7天搞定懒人早起法（具体+有用）”          |
| **内容营销法** | 先提供价值，再自然引流                               | “护肤误区盘点→推荐自家产品”             |
| **心理触发词** | 稀缺、独家、惊喜、免费                               | “仅限今日”“错过可惜”“限量100份”        |


## 九、整合设计思维：跨平台一致性

| 层面     | 要点         | 示例                          |
| ------ | ---------- | --------------------------- |
| 品牌声音统一 | 人格一致，语调可变  | 可口可乐：微博“热情”、电商“清爽”，核心仍是“快乐” |
| 内容主题一致 | 多渠道讲同一故事   | 新品发布：视频讲故事→图文展示→推文引流        |
| 视觉语言协同 | 文案关键词与视觉同步 | “轻盈”“能量”贯穿色调、字形与配图          |


## 实例对照表（多平台一致传播）

| 场景    | 微博文案                 | 小红书文案               | 电商详情页              |
| ----- | -------------------- | ------------------- | ------------------ |
| 面膜新品  | “3分钟=重启好气色💫#换季急救#”  | “熬夜党救星😭敷完皮肤亮到爆✨”   | “快速吸收，深层补水，换季不干皮。” |
| 轻奢咖啡机 | “每天清晨的高级感☕️#家电也能很美#” | “颜值控必入‼️这咖啡机也太美了🥹” | “金属质感·一键萃取·静音设计。”  |


## 十、总结：营销文本的五层思考模型

1. **受众层**：我在对谁说？
2. **目标层**：希望他们做什么？
3. **内容层**：要传递什么价值与情绪？
4. **形式层**：在哪个平台，以何种节奏？
5. **整合层**：跨平台如何保持一致？


"""

