from typing import Any, AsyncGenerator

from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest
from google.genai.types import Part, Content, Blob

from src.logger import logger
from src.agents.experts.usage_utils import parse_usage_obj



async def image_to_prompt_tool(ctx: InvocationContext, input_name: str) -> AsyncGenerator[str, None]:
    system_prompt = '''
## 系统角色设定

你是一名专业的图像提示词反推与分析专家，擅长从任何图像中提取关键信息，并将这些信息转化为清晰、结构化、高质量的扩散模型提示词（包括 nano banana、seedream、gpt-image、Stable Diffusion / Midjourney / DALL·E 系列 / Flux 系列等）。
你的任务是：**从给定的图像中反推出最可能用于生成该图像的 Prompt**，并按照规范化结构输出。

你必须：

1. **精确观察图像内容**，分析：

   * 主体（人物/物体/角色/动物等）
   * 动作、姿态、表情
   * 场景、背景、环境
   * 风格（写实、二次元、油画、赛博朋克…）
   * 摄影参数（若相关：焦段、景深、光线、镜头类型）
   * 色彩、氛围、构图元素
   * 细节修饰词（纹理、材质、质感）

2. **反推最可能的提示词构成方式**，
   如：

   * “prompt 主体 + 修饰词 + 风格 + 相机参数 + 质量词”
   * “艺术家风格 + 构图描述 + 环境 + 纹理 + 色调”

3. **按固定格式输出结果：**

---

## **🔶 Output Format（输出格式）**


### **1. Long Prompt（长提示词）**

包含多个维度的完整提示词，如：

* 主体
* 风格
* 构图
* 光线
* 氛围
* 画质词（例如：highly detailed, 8k, ultra realistic）

### **2. Negative Prompt（反向提示词）**

为了减少模型生成噪点、畸形、错手等问题，自动推测适合的 negative prompt。

### **3. Key Attributes Breakdown（关键属性拆解）**

按类别分析图像内容，方便理解提示词组成。

---

## **🔶 规则要求**

* 不夸大图像中不存在的内容
* 不做臆测性的“故事补全”，只描述可见信息
* 输出风格简洁、专业、结构化
* 保持可直接用于 Stable Diffusion / MJ / DALL·E 的格式
* 如果有不确定，使用“可能”、“推测”为措辞

---

## **🔶 示例输出风格**

**Long Prompt:**
“a futuristic cyberpunk female character, detailed face, wet reflections, neon city street at night, rain particles, dramatic rim lighting, shallow depth of field, high-contrast color palette, ultra-realistic textures, 8k, cinematic atmosphere”

**Negative Prompt:**
“distorted hands, blurry face, low-resolution, extra limbs, artifacts, deformed anatomy, bad lighting”


## 重点注意
 - 风格、布局、文字需要重点描述。防止复刻的时候出现错误。
 - 布局需要描述图像尺寸、文字的位置、主体图像、装饰元素等重要元素的位置，越详细越好。
 - 不用 ControlNet ，也不用 LORA。
 - OCR 需要准确，保持原本的语言类型。不要随意改变图像上文字语言的种类。主要、重要的文字不要遗漏。

## 输出要求
 - 只输出prompt即可以，不用解释。也不用其他说明。

'''

    try:
        # artifact_part = await ctx.load_artifact(filename=input_name)
        artifact_part = await ctx.artifact_service.load_artifact(filename=input_name,
                                                            app_name=ctx.session.app_name,
                                                            user_id=ctx.session.user_id,
                                                            session_id=ctx.session.id)
        def before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
            llm_request.contents.append(
                Content(
                    role="user",
                    parts=[
                        Part(
                            inline_data=Blob(
                                mime_type=artifact_part.inline_data.mime_type,
                                data=artifact_part.inline_data.data,
                            )
                        ),
                        Part(text=system_prompt),
                    ],
                )
            )

        llm = LlmAgent(
            name="image_to_prompt_tool",
            model="gemini-3-pro-preview",
            instruction="Convert the input image into a high quality reverse prompt.",
            include_contents="none",
            before_model_callback=before_model_callback,
        )

        output_text = ""
        usage = None
        async for event in llm.run_async(ctx):
            parsed_usage = parse_usage_obj(event)
            if parsed_usage:
                usage = parsed_usage
            if event.is_final_response() and event.content and event.content.parts:
                generated_text = next((part.text for part in event.content.parts if part.text), None)
                if generated_text:
                    output_text = generated_text

        if output_text:
            return {
                'status': 'success',
                'message': output_text,
                "provider": "gemini",
                "model_name": "gemini-3-pro-preview",
                "usage": usage,
            }
        else:
            return {
                'status': 'error',
                'message': "Image to Prompt 调用失败",
                "provider": "gemini",
                "model_name": "gemini-3-pro-preview",
                "usage": usage,
            }

    except Exception as e:
        error_text = f"Image to Prompt 出错：{str(e)}"
        logger.error(error_text)
        return {
            'status': 'error',
            'message': error_text,
            "provider": "gemini",
            "model_name": "gemini-3-pro-preview",
            "usage": None,
        }
