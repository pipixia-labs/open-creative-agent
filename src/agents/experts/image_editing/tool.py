from typing import Dict, Any, AsyncGenerator, List, ByteString
from http import HTTPStatus
import httpx
import asyncio
from PIL import Image
from io import BytesIO
import os
import base64
import json

from google.adk.tools import ToolContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest
from src.llm.model_factory import build_model_and_config
from google.genai.types import Part, Content, Blob

from google.genai import types


from volcengine.visual.VisualService import VisualService
from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime.types.images.images import SequentialImageGenerationOptions

from conf.api import API_CONFIG
from conf.system import SYS_CONFIG
from src.logger import logger
from src.utils import clean_json_string
from src.agents.experts.usage_utils import parse_usage_obj
from server.services.token_usage_service import token_usage_service

segmind_timeout = httpx.Timeout(None, connect=5.0)
imgbb_timeout = httpx.Timeout(None, connect=5.0)

async def prompt_enhancement_tool(llm_model:str, ctx: InvocationContext, prompt: str) -> AsyncGenerator[str, None]:
    system_prompt = """
# 角色
你是一个专业的提示词优化专家，精通图像编辑模型的提示词具体化和优化工作。

# 任务
你的任务是将精修类型的prompt 进行润色和扩写。因为此类任务用户描述的一般不是特别清楚。
对于非精修类型的prompt（比如删除某个物体、将img1中的衣服传到img2中的模特身上等）你需要保持原先的prompt不变。
如果给你的是多个图像的指令，请将其分开，分别润色，并输出成一个list。


# 各种类型图像精修需要的操作知识
## 证件照
基础调整：曝光、白平衡、对比度
皮肤修饰：轻微磨皮、去痘印/黑眼圈，但保持真实
五官修正：轻微液化（如脸型对称）、美白牙齿
背景处理：统一背景颜色（蓝/白/红），去除杂色
整体要求：自然、干净、端正，避免过度修饰

## 电商照片（商品图/模特图）
基础调整：亮度、饱和度、色彩校正，确保商品颜色真实
细节修饰：去除灰尘、折痕、杂物，突出商品质感
模特修饰：适度磨皮、调整身材比例，保持自然
背景处理：常用纯色/渐变/透明背景，或者统一场景背景
整体要求：突出商品卖点，保证色差小于实物

## 写真（个人写真/艺术照）
基础调整：营造氛围感（柔和/清新/暗调）
皮肤修饰：精细磨皮、频率分离、肤色均匀
五官修饰：美化眼睛、嘴唇，适度液化脸型/身材
光影塑形：通过加深/减淡工具增强立体感
背景与氛围：可虚化背景或调色统一氛围
整体要求：美观、唯美，有艺术感

## 时尚杂志（大片/广告）
基础调整：高对比、强烈色彩或黑白风格，突出时尚感
皮肤修饰：高级修图（频率分离+修容），保持质感
五官与身材：大胆液化调整（腿更长、脸更小、腰更细）
光影与色调：风格化处理，突出戏剧性（冷艳/摩登/复古）
背景与元素：可能更换背景、添加特效或文字排版
整体要求：极致、个性化、视觉冲击力强

## 总结
证件照：真实 → 干净自然
电商照：真实 + 突出商品 → 统一规范
写真：美化 → 自然+唯美氛围
时尚杂志：艺术化 → 夸张+风格化


#  照片精修 Prompt 对照表

## 1. 证件照（ID Photo）

**英文 Prompt：**

```
Enhance portrait for ID photo, natural skin retouch, remove acne and blemishes, even skin tone, brighten eyes, slight teeth whitening, adjust background to plain blue/white/red, keep natural and realistic look, professional ID style.
```

**中文说明：**
精修证件照，肤色均匀、去除痘印和瑕疵，眼睛提亮、牙齿轻微美白，背景更换为蓝/白/红色，保持自然真实效果，适合证件要求。


## 2. 电商照片（E-commerce Product Photo）

**英文 Prompt：**

```
Product photo retouch, enhance sharpness and details, remove dust and wrinkles, smooth fabric, brighten colors to match real product, clean white background, high clarity, professional e-commerce photography style.
```

**中文说明：**
电商商品图精修，突出细节与质感，去除灰尘/褶皱，颜色真实还原，背景纯净白色或透明，清晰度高，专业电商摄影风格。


## 3. 写真（Portrait Photography）

**英文 Prompt：**

```
Fine art portrait retouch, smooth skin with natural texture, frequency separation effect, brighten eyes, enhance lighting and shadows for depth, adjust face shape slightly, cinematic color grading, soft and dreamy atmosphere.
```

**中文说明：**
个人写真精修，自然磨皮保留皮肤质感，明亮眼睛，利用光影塑形增强立体感，轻微调整脸型，色彩风格偏电影质感，营造柔和梦幻氛围。


## 4. 时尚杂志（Fashion Editorial）

**英文 Prompt：**

```
High-fashion editorial retouch, dramatic lighting, smooth but textured skin, bold makeup enhancement, sharpen details, elongate body proportions, artistic background, bold and striking colors, stylish magazine cover look.
```

**中文说明：**
时尚大片精修，光影强烈，皮肤细腻但有质感，强化妆容和细节，适度拉长身材比例，背景可艺术化或夸张处理，色彩前卫，整体有杂志封面感。


## 5. 去杂物/背景处理（Background/Object Removal）

**英文 Prompt：**

```
Remove unwanted objects from background, keep subject sharp and natural, seamless blending, replace background with clean plain color or realistic environment, professional look.
```

**中文说明：**
去除背景杂物，主体清晰自然，过渡无痕，可替换为纯色背景或逼真环境，效果专业。


## 提示优化词汇（可加在结尾）

* **质量提升**：high quality, 8K, ultra realistic, professional retouch
* **风格化**：cinematic, soft light, glossy, studio lighting, editorial style
* **自然真实**：realistic, natural texture, photo-realistic, subtle editing


# 注意事项
 - 你只需要输出优化后的提示词文本，不要输出md或json对象。
 - 如果任务需要在图像上呈现文字，一定保证文字清晰可读。
 - 如果不是精修类型的prompt，就不要改变原先的prompt，直接原封不动返回就好。

# 输出格式要求
输出为json格式
```json
{
result_prompt: [] # 这里放润色之后的prompt。如果给你的是多个prompt的文本，你需要将其分开润色，并将结果放在这个list里面。
}
```
"""

    def before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
        design_suggestions = callback_context.state.get('design_suggestions', '')
        if design_suggestions and len(design_suggestions) > 0:
            design_suggestions = design_suggestions + f"当前设计专家智能体 ArtKnowledgeAgent 给的设计建议是：{design_suggestions} \n\n"
            design_suggestions = design_suggestions + """
注意：这些建议中可能会有多种需要探索的方案，但是你现在需要优化的是其中的一种，
需要优化的prompt将会在下面描述。你需要关注你需要优化的哪一种，然后参考相建议中对应的细节信息进行优化。不要混淆其他方案中的细节。\n\n
"""

            user_prompt = design_suggestions +  f"这是你当前需要优化的 prompt：\n{prompt}。\n请参考ArtKnowledgeAgent 给的设计建议，对其进行润色或扩写。\n\n"
        else:
            user_prompt = f"这是用户输入的原始 prompt：\n{prompt}。\n请对其进行润色或扩写。\n\n"

        llm_request.contents.append(Content(role='user', parts=[Part(text=user_prompt)]))

    # llm_model = SYS_CONFIG.llm_model
    llm_model, llm_config = build_model_and_config(llm_model)

    llm = LlmAgent(
        name="prompt_enhancement",
        model=llm_model,
        generate_content_config=llm_config,
        instruction=system_prompt,
        include_contents='none',
        before_model_callback=before_model_callback
    )

    try:
        enhanced_prompt = None
        async for event in llm.run_async(ctx):
            await token_usage_service.record_event_usage(
                user_id=ctx.session.user_id,
                session_id=ctx.session.id,
                event=event,
                component="expert_tool",
                agent_name="ImageEditingPromptEnhancementTool",
            )
            if event.is_final_response() and event.content and event.content.parts:
                generated_text = next((part.text for part in event.content.parts if part.text), None)
                if generated_text:
                    enhanced_prompt = generated_text
        if enhanced_prompt:
            enhanced_prompt = clean_json_string(enhanced_prompt)
            result_prompt = json.loads(enhanced_prompt)
            if 'result_prompt' in result_prompt:
                result_prompt = result_prompt['result_prompt']
            else:
                result_prompt = []
            return {
                'status': 'success',
                'message': result_prompt
            }
        else:
            return {
                'status': 'error',
                'message': "LLmAgent调用失败"
            }


    except Exception as e:
        error_text = f"prompt_enhancement in image_editing_agent 出错：{str(e)}"
        logger.error(error_text)
        return {
            'status': 'error',
            'message': error_text
        }


async def segmind_GPT_image_1_tool(tool_context: ToolContext, enhance_prompt_list) -> AsyncGenerator[Dict, None]:
    current_parameters = tool_context.state.get("current_parameters",{})
    input_name = current_parameters.get("input_name")
    tool_name_log = "segmind_GPT_image_1_tool"
    original_prompt = current_parameters.get("prompt")
    # prompt = current_parameters.get("enhanced_prompt")
    prompt = enhance_prompt_list

    # logger.debug('prompt for image editing: ' + '\n'.join(prompt))


    count = len(prompt)
    
    if isinstance(input_name, str):
        input_name = [input_name]
    if isinstance(prompt, str):
        prompt = [prompt]

    img_binary_list = []
    for name in input_name:
        art_part = await tool_context.load_artifact(name)
        img_binary_list.append(art_part.inline_data.data)

    tasks = [upload_local_image(img_binary) for img_binary in img_binary_list]
    img_list = await asyncio.gather(*tasks)

    tasks = [call_segmind_API(img_list, p) for p in prompt]
    result_list = await asyncio.gather(*tasks)

    result = {
        'status': "success",
        'message': [],
        'provider': 'segmind',
        'model_name': 'gpt-image-1-edit',
        'usage_list': [],
    }
    success_num = 0
    for item in result_list:
        if item['status'] == 'success': 
            result['message'].append(item['message'])
            result['usage_list'].append(item.get('usage'))
            success_num += 1
        else:
            result["message"].append(None)
            result["usage_list"].append(None)
    
    if success_num==0:
        result['message'] = f"{count}张图片全部生成失败，原因包括：{','.join([item['message'] for item in result_list])}"
        result['status']='error'

    return result
    

async def upload_local_image(image_binary:ByteString, expiration:int=600, name:str=None):
    api_key = os.environ.get("IMGBB_API_KEY")
    if not api_key:
        raise RuntimeError("IMGBB_API_KEY is not set. Please export IMGBB_API_KEY before uploading images.")
    url = "https://api.imgbb.com/1/upload"

    files = {"image": image_binary}

    params = {
        "key": api_key,
        "expiration": expiration,
        "name": name,
    }
    
    try:
        async with httpx.AsyncClient(timeout=imgbb_timeout) as client:
            response = await client.post(url, params=params, files=files)

        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            data = result["data"]
            print("Upload succeeded.")
            print("Image ID:", data["id"])
            print("Viewer URL:", data["url_viewer"])
            print("Direct URL:", data["url"])
            return data["url"]
        else:
            print(f"Upload failed, status code: {result['status']}")
            print("Error:", result.get("error", "No details"))
            return None
    except httpx.TimeoutException as e:
        logger.info(f"Image upload request timed out: {str(e)}")
        return None
    except httpx.RequestError as e:
        logger.info(f"Image upload request failed: {str(e)}")
        return None
    
async def call_segmind_API(img_list: List, prompt: str):
    SEGMIND_API_KEY = API_CONFIG.SEGMIND_API_KEY
    url = "https://api.segmind.com/v1/gpt-image-1-edit"

    headers = {'x-api-key': SEGMIND_API_KEY}
    data = {
        "prompt": prompt,
        "image_urls": img_list,
        "size": "auto",
        "quality": "auto",
        "background": "opaque",
        "output_compression": 100,
        "output_format": "png",
        "moderation": "auto"
    }

    try:
        attempt = 0
        while(attempt < 3):
            logger.info("calling segmind GPT-image-1 API ...")
            #response = requests.post(url, json=data, headers=headers)
            async with httpx.AsyncClient(timeout=segmind_timeout) as client:
                response = await client.post(url, headers=headers, json=data)
            logger.info("Image editing completed.")

            if response.status_code == HTTPStatus.OK:
                content = response.content
                return {"status": "success", "message": content, "usage": None}

            attempt += 1
            logger.info(f"Error generating image: status code:{response.status_code}: {response.content[:500]}")
                
        logger.info("Maximum retry count reached; image editing failed.")
        return {"status": "error", "message": f"{response.status_code}: {response.content[:500]}", "usage": None}
    except httpx.TimeoutException as e:
        logger.info("Segmind API request failed: timeout")
        return {"status": "error", "message": "Segmind API request failed: timeout", "usage": None}
    except Exception as e:
        logger.info(f"Segmind API Request failed: {str(e)}")
        return {"status": "error", "message": f"{str(e)}", "usage": None}


async def nano_banana_image_edit_tool(tool_context: ToolContext, enhance_prompt_list) -> AsyncGenerator[Dict, None]:
    current_parameters = tool_context.state.get("current_parameters", {})
    input_name = current_parameters.get("input_name")
    # tool_name_log = "segmind_GPT_image_1_tool"
    # original_prompt = current_parameters.get("prompt")
    # prompt = current_parameters.get("enhanced_prompt")
    prompt = enhance_prompt_list

    # logger.debug('prompt for image editing: ' + '\n'.join(prompt))

    count = len(prompt)

    if isinstance(input_name, str): input_name = [input_name]
    if isinstance(prompt, str): prompt = [prompt]

    invocation_ctx = getattr(tool_context, "_invocation_context", None)
    if invocation_ctx is None:
        return {"status": "error", "message": "ToolContext missing invocation context"}

    img_binary_list = []
    for name in input_name:
        art_part = await tool_context.load_artifact(name)
        img_binary_list.append(art_part.inline_data.data)

    try:
        # result_list = []
        success_num = 0
        result = {
            'status': "success",
            'message': [],
            'provider': 'gemini',
            'model_name': 'gemini-3.1-flash-image-preview',
            'usage_list': [],
        }
        fail_message = []
        for p in prompt:
            input_images: list[Image.Image] = []
            for img in img_binary_list:
                input_images.append(Image.open(BytesIO(img)))

            def before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest):
                user_parts: list[Part] = [Part(text=p)]
                for img_obj in input_images:
                    buffer = BytesIO()
                    img_obj.save(buffer, format="PNG")
                    user_parts.append(
                        Part(inline_data=Blob(mime_type="image/png", data=buffer.getvalue()))
                    )
                llm_request.contents.append(Content(role="user", parts=user_parts))

            llm = LlmAgent(
                name="image_editing_nano_banana",
                model="gemini-3.1-flash-image-preview", # "gemini-3-pro-image-preview",
                instruction="Edit image(s) according to prompt.",
                include_contents="none",
                before_model_callback=before_model_callback,
            )

            text_message = ''
            img_message = ''
            usage = None
            async for event in llm.run_async(invocation_ctx):
                parsed_usage = parse_usage_obj(event)
                if parsed_usage:
                    usage = parsed_usage
                if not event.content or not event.content.parts:
                    continue
                for part in event.content.parts:
                    if part.text is not None:
                        text_message = part.text
                    elif part.inline_data is not None:
                        img_message = part.inline_data.data
            if img_message is not None:
                # result = {'status': "success", "message": img_message}
                success_num = success_num + 1
                result['message'].append(img_message)
                result['usage_list'].append(usage)
            else:
                result['message'].append(None)
                result['usage_list'].append(usage)
                fail_message.append(text_message)
                # result = {'status': "error", "message": text_message}

            # result_list.append(result)


        if success_num == 0:
            result['message'] = f"All {count} image edits failed. Reasons: {','.join(fail_message)}"
            result['status'] = 'error'

        return result

    except Exception as e:
        error_msg = f"[nano_banana_image_edit_tool] failed: {e}"
        logger.error("[nano_banana_image_edit_tool] failed: {}", e, exc_info=True)
        return {"status": "error", "message": error_msg}

def read_image(filename):
    ext = filename.split(".")[-1]
    with open(filename, "rb") as f:
        img = f.read()
    data = base64.b64encode(img).decode()
    src = "data:image/{ext};base64,{data}".format(ext=ext, data=data)
    return src

async def seedream_image_edit_tool(tool_context: ToolContext, enhance_prompt_list) -> AsyncGenerator[dict[str, Any], None]:
    logger.info("calling seedream for image editing ...")

    current_parameters = tool_context.state.get("current_parameters", {})
    input_name = current_parameters.get("input_name")
    # tool_name_log = "segmind_GPT_image_1_tool"
    # original_prompt = current_parameters.get("prompt")
    # prompt = current_parameters.get("enhanced_prompt")
    prompt = enhance_prompt_list

    # logger.debug('prompt for image editing: ' + '\n'.join(prompt))

    count = len(prompt)

    if isinstance(input_name, str): input_name = [input_name]
    if isinstance(prompt, str): prompt = [prompt]


    img_bs64_list = []
    for name in input_name:
        art_part = await tool_context.load_artifact(name)
        ext = name.split(".")[-1]

        img_bin = art_part.inline_data.data
        data = base64.b64encode(img_bin).decode()
        data_bs64 = "data:image/{ext};base64,{data}".format(ext=ext, data=data)
        img_bs64_list.append(data_bs64)


    try:
        ARK_API_KEY = os.environ.get('ARK_API_KEY')
        client = Ark(
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=ARK_API_KEY,
        )
        success_num = 0
        result = {
            'status': "success",
            'message': [],
            'provider': 'seedream',
            'model_name': 'doubao-seedream-4-0-250828',
            'usage_list': [],
        }
        fail_message = []

        for p in prompt:
            imagesResponse = client.images.generate(
                model="doubao-seedream-4-0-250828",
                prompt=p,
                image=img_bs64_list,
                size="2K",
                sequential_image_generation="auto",
                sequential_image_generation_options=SequentialImageGenerationOptions(max_images=10),
                response_format="b64_json",
                watermark=False
            )

            if imagesResponse.error:
                fail_message.append(imagesResponse.error)
                result['message'].append(None)
                result['usage_list'].append(parse_usage_obj(imagesResponse))
            else:
                img_bs64_data = imagesResponse.data[0].b64_json
                img_bin_data = base64.b64decode(img_bs64_data)
                result['message'].append(img_bin_data)
                result['usage_list'].append(parse_usage_obj(imagesResponse))
                success_num = success_num + 1

        if success_num == 0:
            result['message'] = f"All {count} seedream image edits failed. Reasons: {','.join(fail_message)}"
            result['status'] = 'error'

        return result

    except Exception as e:
        error_msg = f"[seedream_image_edit_tool] failed: {e}"
        logger.error("[seedream_image_edit_tool] failed: {}", e, exc_info=True)
        return {"status": "error", "message": error_msg}
