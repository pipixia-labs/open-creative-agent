import io
import json
import os
import time
from typing import Optional

import requests
from PIL import Image
from io import BytesIO

from alibabacloud_imageseg20191230.client import Client as ImageSegClient
from alibabacloud_imageseg20191230.models import (
    # SegmentHDCommonImageRequest,
    SegmentHDCommonImageAdvanceRequest,
    GetAsyncJobResultRequest,
)
from alibabacloud_tea_openapi.models import Config
from alibabacloud_tea_util.models import RuntimeOptions

def get_image_info_from_bytes(image_bytes):
    """Decode image bytes and return basic size and transparency information."""
    if not isinstance(image_bytes, (bytes, bytearray)):
        return '图片未成功生成或字节数据无效。'

    try:
        image_stream = io.BytesIO(image_bytes)
        with Image.open(image_stream) as img:
            width, height = img.size
            result = f"Image width: {width}, Image height: {height}\n"

            if img.mode == "P":
                if "transparency" in img.info:
                    result += "**该图片具有透明度 (P 模式带透明信息)。**"
                    return result

            if img.mode in ("RGBA", "LA", "PA"):
                alpha_channel = img.split()[-1]



                min_alpha, max_alpha = alpha_channel.getextrema()

                if min_alpha < 255:
                    result += "该图片实际具有透明度 (Alpha 最小值 < 255)。"
                else:
                    result += "该图片具有 Alpha 通道，但实际内容为完全不透明 (所有 Alpha 值 = 255)。"

                return result

            result += "该图片不具有透明度 (无 Alpha 通道)。"
            return result

    except Exception as e:
        return f"获取图像基本信息失败：{e}"

# def get_image_info_from_bytes(image_bytes):
#     """
#     """
#     if not isinstance(image_bytes, (bytes, bytearray)):
#     try:
#         image_stream = io.BytesIO(image_bytes)
#         with Image.open(image_stream) as img:
#             width, height = img.size
#             result = f"Image width: {width}, Image height: {height}\n"
#                 if img.mode == "P" and "transparency" not in img.info:
#                 else:
#             else:
#             return result
#     except Exception as e:



def _create_imageseg_client() -> ImageSegClient:
    """Create an Aliyun image segmentation client from configured credentials."""
    access_key_id = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID")
    access_key_secret = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET")

    if not access_key_id or not access_key_secret:
        raise RuntimeError(
            "Aliyun AccessKey credentials are missing. Please set "
            "ALIBABA_CLOUD_ACCESS_KEY_ID and ALIBABA_CLOUD_ACCESS_KEY_SECRET."
        )

    config = Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        endpoint="imageseg.cn-shanghai.aliyuncs.com",
        region_id="cn-shanghai",
    )
    return ImageSegClient(config)


def _poll_async_job_result(
    client: ImageSegClient,
    job_id: str,
    *,
    interval_seconds: float = 2.0,
    max_retries: int = 6,
) -> Optional[bytes]:
    """Poll an Aliyun image segmentation job until it returns result bytes or fails."""
    for _ in range(max_retries):
        get_req = GetAsyncJobResultRequest(job_id=job_id)
        get_resp = client.get_async_job_result(get_req)
        result = get_resp.body

        status = result.data.status

        if status == "PROCESS_SUCCESS":
            json_obj = json.loads(result.data.result)
            img_url = json_obj.get("imageUrl")
            if not img_url:
                print("No imageUrl field found in the async job result.")
                # return None
                continue

            try:
                resp = requests.get(img_url, timeout=30)
                resp.raise_for_status()
                return resp.content
            except Exception as e:
                print(f"Failed to download result image {img_url}: {e}")
                # return None
                continue

        if status in ("FAILED", "FAILURE", "ERROR"):
            print(f"Async image segmentation job failed. status={status}, detail={result}")
            # return None
            continue
        time.sleep(interval_seconds)

    print("Polling timed out before the async image segmentation job succeeded.")
    return None



def make_background_transparent_bytes(image_bytes: bytes) -> bytes:
    """Remove an image background with Aliyun image segmentation and return PNG bytes."""

    try:
        client = _create_imageseg_client()

        # segment_req = SegmentHDCommonImageRequest()
        segment_req = SegmentHDCommonImageAdvanceRequest()

        segment_req.image_url_object = BytesIO(image_bytes)

        runtime = RuntimeOptions(
            read_timeout=30000,
            connect_timeout=10000
        )

        submit_resp = client.segment_hdcommon_image_advance(segment_req, runtime)
        submit_body = submit_resp.body
        job_id = submit_body.request_id

        if not job_id:
            print("Image segmentation job submission failed: missing job_id.")
            return b""

        result_bytes = _poll_async_job_result(client, job_id)
        if result_bytes is None:
            return b""

        return result_bytes

    except Exception as error:
        print("Aliyun image segmentation request failed:", error)
        if hasattr(error, "code"):
            print("Error code:", getattr(error, "code"))
        return b""

def _ratio_to_float(r):
    a, b = map(float, r.split(':'))
    return a / b

def select_aspect_ratio(as_in:str, as_list=['1:1', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9', '21:9']):
    if as_in is None or (not isinstance(as_in, str)) :
        return '1:1'

    if ':' not in as_in:
        return '1:1'

    as_in_value = _ratio_to_float(as_in)
    min_index = 0
    d = 99999
    for i, a in enumerate(as_list):
        v = _ratio_to_float(a)
        if abs(v - as_in_value) < d:
            min_index = i
            d = abs(v - as_in_value)

    return as_list[min_index]
