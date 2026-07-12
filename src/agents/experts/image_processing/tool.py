from typing import Any, AsyncGenerator


from src.logger import logger
from src.agents.experts.image_utils import make_background_transparent_bytes


async def image_processing_tool(input_image_bytes: list, processing_type:str='') -> AsyncGenerator[dict[str, Any], None]:
    """Process input image bytes and return processed image bytes."""
    logger.info("calling image_processing_tool for image processing ...")

    try:
        result_bytes_list = []
        if processing_type == 'background_transparent':
            for image in input_image_bytes:
                t = make_background_transparent_bytes(image)
                result_bytes_list.append(t)


        if result_bytes_list is not None and len(result_bytes_list) > 0:
            logger.info(f"Image processing completed with {len(result_bytes_list)} result(s).")
            result = {'status': "success", "message": result_bytes_list}
        else:
            result = {'status': "error", "message": "Image processing failed."}

        return result

    except Exception as e:
        error_msg = f"[image_processing_tool] failed: {e}"
        logger.error("[image_processing_tool] failed: {}", e, exc_info=True)
        return {"status": "error", "message": error_msg}
