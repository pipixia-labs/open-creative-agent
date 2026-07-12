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
from src.agents.experts.image_utils import get_image_info_from_bytes

async def pgbr_design_element_analysis_before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
    """Add session state and artifact context to the model request before generation."""
    current_parameters = callback_context.state.get('current_parameters', {})

    if 'task_query' in current_parameters:
        input_text = f"当前的任务是：{current_parameters['task_query']}\n"
        llm_request.contents.append(Content(role='user', parts=[Part(text=input_text)]))


    reference_image_name = current_parameters.get('reference_image_name', '')
    if reference_image_name is not None and len(reference_image_name) > 0:
        art_part = await callback_context.load_artifact(filename=reference_image_name)

        basic_info = get_image_info_from_bytes(art_part.inline_data.data)
        artifact_parts = [Part(text=f"你参考图像的名字为:{reference_image_name}。\n其基本信息为：{basic_info}\n，以下是图片的内容：\n")]
        artifact_parts.append(art_part)

        llm_request.contents.append(Content(role='user', parts=artifact_parts))
    return


class PGBRDesignElementAnalysisAgent(BaseAgent):
    model_config = {"arbitrary_types_allowed": True}
    llm: LlmAgent

    def __init__(self, name: str, description: str = '', llm_model: str = ''):
        if not llm_model:
            llm_model = SYS_CONFIG.llm_model
        logger.info(f"PGBRDesignElementAnalysisAgent: using llm: {llm_model}")

        llm_model, llm_config = build_model_and_config(llm_model)

        llm = LlmAgent(
            name=name,
            model=llm_model,
            generate_content_config=llm_config,
            description=description,
            include_contents='none',
            instruction=pgbr_design_element_analysis_instruction,
            before_model_callback=pgbr_design_element_analysis_before_model_callback,
            output_key = "page_generation_by_reference/element_analysis_results"
        )

        super().__init__(
            name=name,
            description=description,
            llm=llm,
        )

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Run the agent asynchronously and yield ADK events."""
        current_parameters = ctx.session.state.get('current_parameters', {})
        if 'task_query' not in current_parameters or 'reference_image_name' not in current_parameters:
            error_text = f"提供给{self.name}的参数缺失，必须包含：task_query 和 reference_image_name"
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
            message = f"PGBRDesignElementAnalysisAgent 生成回复失败"
            message_for_user = "生成回复失败"
            logger.error(message)
            current_output = {"author": self.name, 'status': 'error', 'message': message, 'message_for_user': message_for_user, 'output_text':''}
        else:
            message = f"PGBRDesignElementAnalysisAgent 已完成分析和代码草稿"
            message_for_user = "已完成分析和代码草稿"
            output_text = '\n'.join(text_list)
            current_output = {"author": self.name, 'status': 'success', 'message': message, 'message_for_user': message_for_user, 'output_text': output_text}

        yield Event(
            author='PGBRDesignElementAnalysisAgent',
            content=Content(role='model', parts=[Part(text=message)]),
            actions=EventActions(state_delta={'current_output': current_output})
        )


pgbr_design_element_analysis_instruction = '''
# 角色
你是一个顶尖的网页设计师，擅长把截图解构成设计元素。后面会有其他智能体利用你解构的结果来执行生成任务。

所以，你的任务是反推设计相关的资产，不要给出具体实现的建议。

# 目标

你分析的图像主要是poster（电影、营销等场景）、网页截图。

你的目标是分析和反推在用**网页+某些待生成资产**来生成这个给定图像需要哪些元素，然后由其他模型负责生成图像，并最终来复刻给定的图像。

你需要将文字、前景图、背景图分解开，并描述其内容、风格、对应的bbox。

不要将图像分的很碎，愿意如下：
 - 如果分的很碎，在复刻的时候，有可能会有图像间有明显分界线的、融合度不够的问题。
 - 用来生成图像的图像生成模型能力很强，可以生成多物体图像。
 - 可以用网页来实现的效果就不要用图像去实现。
 - 尽量用数量更少的图像素材


# 至少需要分离以下的设计元素
 - 标题、副标题、文字，字体大小、字体类型、风格、位置、排版、对齐关系等。
 - 主体图等主要的图像素材，务必要分解出来，并且需要描述bbox。输出bbox的左上角和右下角。
 - 布局，你需要细致分析当前页面的排版，要保证用网页复刻的排版布局（文字、图像的相对位置和绝对位置）和给定的参考图一致。
 - 背景图，如果截图有背景图，你也需要将其分解出来。
 - **每个**设计元素都需要用bbox来把按照坐标和大小描述出来。

# 分析方法
采用先整体在局部的视觉分析方法。具体如下：
 - 整体布局：从整体上分析视觉画面，可以考虑的点有视觉区域位置、大小、占比，文字信息区域的位置、大小、占比等信息。整体布局对于视觉效果很重要。
 - 分析完整体之后，分析各个大的组成部分里面的元素。比如视觉主体区域的组成元素和信息发布区的组成元素。各个组成元素都需要位置、风格、文本信息等细节信息。

# 输出布局要求

布局分析结果以 JSON 形式来表达，它包含以下结构:

## 1. 画布(Canvas)信息
```json
{{
  "canvas": {{
    "width": 1080,        // Canvas width (px)
    "height": 1920,       // Canvas height (px)
    "background": "#f5f5f5" // Background color (hex/rgb/rgba/gradient supported)
  }}
}}
```

## 2. 元素(Elements)列表

每个元素必须包含以下核心属性:

### 通用属性(所有元素)
- **id**: 唯一标识符(字符串,如 "bg-image-1", "title-text-1")
- **type**: 元素类型,可选值:
  - `"image"` - 需要生成的图像
  - `"text"` - 文本内容
  - `"shape"` - 装饰性形状(矩形/圆形/线条等)
  - `"group"` - 元素组(用于组织相关元素)
- **parentId**: 父元素ID(null 表示根元素,其他表示嵌套关系)
- **x, y**: 位置坐标(px,相对于父元素)
- **w, h**: 宽度和高度(px)
- **zIndex**: 层级(数字,越大越在上层,范围 0-100)

### 视觉样式属性
- **opacity**: 不透明度(0-1)
- **transform**: CSS transform 值(如 "rotate(45deg)", "scale(1.2)")
- **filter**: CSS filter 值(如 "blur(10px)", "brightness(1.2)")
- **radius**: 圆角(如 "8px", "50%")
- **shadow**: 阴影(CSS box-shadow 值)

### Image 类型特有属性
```json
{{
  "type": "image",
  "attributes": {{
    "description": "详细的图像描述,用于文生图模型生成。需包含:主体、风格、构图、色调、光线等",
    "alt": "图像的替代文本",
    "fit": "cover|contain|fill", // Image fit mode
    "prompt": "完整的文生图 prompt(可选,如果你想直接指定)"
  }}
}}
```

### Text 类型特有属性
```json
{{
  "type": "text",
  "attributes": {{
    "content": "文本内容",
    "fontSize": 48,              // Font size (px)
    "fontFamily": "Noto Sans",   // Font family, e.g. "Inter", "Noto Sans", "Arial"
    "fontWeight": "400|500|700|900", // Font weight
    "color": "#ffffff",          // Text color
    "textAlign": "left|center|right",
    "lineHeight": 1.5,           // Line height
    "letterSpacing": 0,          // Letter spacing (px)
    "textShadow": "0px 2px 4px rgba(0,0,0,0.3)", // Optional text shadow
    "styles": [                  // Optional inline styles
      {{
        "selection": [0, 5],     // Character range
        "color": "#ff0000"       // Color for this range
      }}
    ]
  }}
}}
```

### Shape 类型特有属性
```json
{{
  "type": "shape",
  "attributes": {{
    "shapeType": "rectangle|circle|line", // Shape type
    "fill": "#ff0000",           // Fill color (gradient supported)
    "stroke": "#000000",         // Stroke color
    "strokeWidth": 2             // Stroke width (px)
  }}
}}
```

### Group 类型特有属性
```json
{{
  "type": "group",
  "attributes": {{
    "backdropFilter": "blur(12px)", // Optional backdrop blur
    "border": "1px solid rgba(255,255,255,0.2)" // Optional border
  }}
}}
```

## 3. 设计原则

在设计时,请遵循以下原则:

1. **视觉层次**
   - 主标题通常 fontSize 80-200px, zIndex 较高
   - 副标题 fontSize 32-64px
   - 正文 fontSize 24-48px
   - 使用 zIndex 明确表达层级关系(背景层 0-10, 内容层 20-50, 前景装饰层 60-80)

2. **布局规范**
   - 保持适当留白(边距通常 48-96px)
   - 重要信息在视觉中心或黄金分割位置
   - 考虑阅读顺序(从上到下,从左到右,Z型或F型)
   - 对齐:相关元素使用统一的 x 或 y 坐标对齐

3. **色彩与对比**
   - 确保文本与背景有足够对比度(深色背景用浅色文字,反之亦然)
   - 使用 opacity 创建层次感
   - 装饰性元素可使用半透明色彩(opacity 0.1-0.3)

4. **图像元素**
   - 背景图像通常 zIndex 1-5, opacity 0.3-0.8
   - 主要内容图像 zIndex 20-30
   - 为图像提供清晰、详细的 description,包含:
     * 主体内容(如"消防员头盔")
     * 视角(俯视/正面/侧面)
     * 风格(写实/3D/插画/扁平)
     * 色调(暖色调/冷色调/黑白)
     * 背景(纯色/渐变/场景)
     * 光线(柔和/强烈/戏剧性)

5. **装饰元素**
   - 使用 shape + filter: blur() 创建光晕效果
   - 使用半透明的 shape 作为色块装饰
   - 使用 group + backdropFilter 创建毛玻璃效果

6. **分组组织**
   - 相关元素使用 group 组织(如日期+地点信息卡片)
   - group 可以有统一的背景、边框、模糊效果
   - 合理使用 parentId 表达嵌套关系

## 4. 输出示例
```json
{{
  "canvas": {{
    "width": 1080,
    "height": 1920,
    "background": "linear-gradient(180deg, #1a1a2e 0%, #16213e 100%)"
  }},
  "elements": [
    {{
      "id": "bg-image-1",
      "type": "image",
      "parentId": null,
      "x": 0,
      "y": 0,
      "w": 1080,
      "h": 1920,
      "zIndex": 1,
      "opacity": 0.4,
      "attributes": {{
        "description": "抽象的深色背景,带有微妙的红色烟雾和火花,电影级光线,minimal纹理,8k分辨率,高对比度",
        "alt": "Background",
        "fit": "cover"
      }}
    }},
    {{
      "id": "decoration-blur-1",
      "type": "shape",
      "parentId": null,
      "x": 100,
      "y": 100,
      "w": 400,
      "h": 400,
      "zIndex": 5,
      "opacity": 0.3,
      "filter": "blur(100px)",
      "attributes": {{
        "shapeType": "circle",
        "fill": "#ff6b6b"
      }}
    }},
    {{
      "id": "main-title",
      "type": "text",
      "parentId": null,
      "x": 90,
      "y": 300,
      "w": 900,
      "h": 200,
      "zIndex": 30,
      "attributes": {{
        "content": "全民消防",
        "fontSize": 120,
        "fontFamily": "Noto Sans",
        "fontWeight": "900",
        "color": "#ffffff",
        "textAlign": "center",
        "lineHeight": 1.2,
        "letterSpacing": 10,
        "textShadow": "0px 10px 30px rgba(0, 0, 0, 0.5)",
        "styles": [
          {{
            "selection": [2, 4],
            "color": "#ff4757"
          }}
        ]
      }}
    }},
    {{
      "id": "info-card-group",
      "type": "group",
      "parentId": null,
      "x": 90,
      "y": 1400,
      "w": 900,
      "h": 200,
      "zIndex": 25,
      "radius": "16px",
      "opacity": 1,
      "attributes": {{
        "fill": "rgba(255, 255, 255, 0.1)",
        "backdropFilter": "blur(20px)",
        "border": "1px solid rgba(255, 255, 255, 0.2)"
      }}
    }},
    {{
      "id": "date-text",
      "type": "text",
      "parentId": "info-card-group",
      "x": 40,
      "y": 80,
      "w": 400,
      "h": 60,
      "zIndex": 26,
      "attributes": {{
        "content": "2025.12.18",
        "fontSize": 48,
        "fontFamily": "Inter",
        "fontWeight": "700",
        "color": "#ffffff",
        "textAlign": "left"
      }}
    }},
    {{
      "id": "hero-image",
      "type": "image",
      "parentId": null,
      "x": 140,
      "y": 700,
      "w": 800,
      "h": 600,
      "zIndex": 20,
      "filter": "contrast(1.1) saturate(1.1)",
      "attributes": {{
        "description": "3D等距渲染的消防员头盔、灭火器和安全盾牌,漂浮在空中,现代风格,红色和橙色配色,工作室光线,干净的背景",
        "alt": "Fire Safety Equipment",
        "fit": "contain",
        "prompt": "3D isometric render of firefighter helmet, fire extinguisher and safety shield, floating, modern style, red and orange color palette, studio lighting, clean background, high quality, 8k"
      }}
    }}
  ]
}}
```
    
# 注意事项
 - 背景图上不要有文字，如果有多种方式来实现背景图，选择一种简单、可靠、步骤少的方式。
 - 图像生成模型能力比较强，有些图像可以一次生成，不一定需要以贴图形式贴到背景图里面。调用图像生成模型次数尽量少。
 - 做元素的分解的时候，可以用网页来实现的就不要用图像生成模型来做，比如规律的几何形状、规律的线条等等。
 - 图像如果需要透明，一定表达出来，加上 `TRANSPARENT` 的字眼。这个字符串会被用来作为透明图像的后处理的 trigger。注意是英文大写。
 - 注意字体类型一定要和参考图一致，所以参考图上的字体类型一定识别正确，字体类型一定识别正确。
 - 注意装饰性质的元素的形状需要和参考图一致。
 - 图像资产务必给出bbox。
 - 你所有的输出内容都来自给你的参考图像，而不是来自用户的任务描述。一定不能有幻觉！！

---

下面开始分析和解构任务
'''

