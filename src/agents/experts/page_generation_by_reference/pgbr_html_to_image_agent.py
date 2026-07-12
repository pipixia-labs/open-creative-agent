import asyncio
from pathlib import Path
import json
from playwright.async_api import async_playwright
import asyncio
import os
# import os.path
import tempfile
from pathlib import Path
import json
import datetime


from typing import AsyncGenerator, List, Dict
from typing_extensions import override



from google.genai.types import Content
from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.tools import ToolContext
from google.genai.types import Part, Blob

from src.logger import logger
from src.agents.experts.html_to_image.tool_v3 import html_to_image
from src.utils import clean_json_string



async def html_to_image(html_code: str, img_binary_list, suggested_width=1024, suggested_height=768):
    async def _scroll_until_stable(page, step=800, idle_checks=3, idle_wait=0.5):
        """Scroll a browser page until lazy-loaded layout height stabilizes."""
        last_height = -1
        stable_count = 0
        while True:
            # await page.emulate_media(media="screen")
            height = await page.evaluate("document.body.scrollHeight")
            if height == last_height:
                stable_count += 1
                if stable_count >= idle_checks:
                    break
                await asyncio.sleep(idle_wait)
            else:
                stable_count = 0
                last_height = height
                for y in range(0, height, step):
                    await page.evaluate(f"window.scrollTo(0, {y})")
                    await asyncio.sleep(0.05)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.3)

    async def _wait_all_images_decoded(page, timeout=60_000):
        """Wait until all page images have completed decoding in the browser."""
        await page.wait_for_function(
            """
            () => {
              const imgs = Array.from(document.images || []);
              if (imgs.length === 0) return true;
              return Promise.all(
                imgs.map(img => {
                  // Already complete
                  if (img.complete && img.naturalWidth > 0) return Promise.resolve(true);
                  // Try decode when the browser supports it
                  if (typeof img.decode === 'function') {
                    return img.decode().then(() => true).catch(() => true);
                  }
                  // Fall back to the load event
                  return new Promise(res => {
                    if (img.complete) return res(true);
                    img.addEventListener('load', () => res(true), { once: true });
                    img.addEventListener('error', () => res(true), { once: true });
                  });
                })
              ).then(() => true);
            }
            """,
            timeout=timeout
        )

    with tempfile.TemporaryDirectory(delete=False) as td:
        html_file_path = os.path.join(td, "index.html")
        with open(html_file_path, "w", encoding="utf-8") as fh:
            fh.write(html_code)

        for img_name, img_bin in img_binary_list:
            safe_name = os.path.basename(img_name)
            with open(os.path.join(td, safe_name), "wb") as fh:
                fh.write(img_bin)

        html = Path(html_file_path)
        error_message = ""
        img_message = None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    device_scale_factor=1.5,
                    viewport={"width": suggested_width, "height": suggested_height},
                    # viewport={"width": 1024, "height": 768},
                )
                page = await context.new_page()

                # logger.info(f"HTML path: {html}")
                url = html.resolve().as_uri()  # file://...
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)

                await page.evaluate("""
                  for (const img of document.querySelectorAll('img')) {
                    if (img.getAttribute('loading') === 'lazy') {
                      img.setAttribute('loading', 'eager');
                    }
                    // Some libraries store the real URL in data-src
                    if (!img.getAttribute('src') && img.getAttribute('data-src')) {
                      img.setAttribute('src', img.getAttribute('data-src'));
                    }
                  }
                """)
                await page.add_style_tag(content="""
                  * { -webkit-backdrop-filter:none !important; backdrop-filter:none !important; }
                """)

                await page.wait_for_load_state("networkidle", timeout=60_000)

                await _scroll_until_stable(page)

                await _wait_all_images_decoded(page, timeout=60_000)

                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.3)

                out_path = os.path.join(td, "out_html.png")
                # await page.screenshot(path=out_path, full_page=True)

                content_h = await page.evaluate(
                    "Math.max(document.documentElement.scrollHeight, document.body.scrollHeight, document.documentElement.clientHeight)")
                content_w = await page.evaluate(
                    "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth, document.documentElement.clientWidth)")
                await page.set_viewport_size({"width": max(1024, int(content_w)), "height": int(content_h)})


                await page.screenshot(path=out_path)
                # logger.info("Saved html screenshot to: %s", out_path)

                await context.close()
                await browser.close()

                with open(out_path, "rb") as f:
                    img_message = f.read()
        except Exception as e:
            error_message = str(e)

        if img_message is not None:
            result = {"status": "success", "message": img_message}
        else:
            result = {"status": "error", "message": error_message}

    return result

class PGBRHTMLToImageAgent(BaseAgent):
    """
    a custom agent for search image or text
    """

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, name: str,description: str = ""):
        super().__init__(name=name, description=description)


    def format_event(self, content_text: str = None, state_delta: Dict = None):
        event = Event(author=self.name)
        if state_delta:
            event.actions = EventActions(state_delta=state_delta)
        if content_text:
            event.content = Content(role='model', parts=[Part(text=content_text)])
        return event


    @override
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Runs the HTMLTOImage asynchronously.
        This method achieves transform html page to a single image.
        Args:
            ctx (InvocationContext): The invocation context for the agent.
        Yields:
            Event: The events generated by the sequential agent during the image generation process.
        """

        pgbr_final_results = ctx.session.state.get('page_generation_by_reference/final_results', {})
        logger.info('log from PGBRHTMLToImageAgent')

        logger.info(pgbr_final_results)
        pgbr_final_results = clean_json_string(pgbr_final_results)
        logger.info(pgbr_final_results)
        pgbr_final_results = json.loads(pgbr_final_results)

        # logger.info(pgbr_final_results)

        html_code = pgbr_final_results['pgbr_html_code_final']
        image_name_list = pgbr_final_results['pgbr_image_name_list']
        if isinstance(image_name_list, str):
            image_name_list = [image_name_list]

        suggested_width = 1024
        suggested_height = 768

        if 'suggested_width' in pgbr_final_results:
            suggested_width = pgbr_final_results['suggested_width']
        if 'suggested_height' in pgbr_final_results:
            suggested_height = pgbr_final_results['suggested_height']

        logger.info(html_code)
        logger.info(image_name_list)


        img_binary_list = []
        for name in image_name_list:
            art_part = await ctx.artifact_service.load_artifact(filename=name,
                                                                app_name=ctx.session.app_name,
                                                                user_id=ctx.session.user_id,
                                                                session_id=ctx.session.id)
            img_binary_list.append((name, art_part.inline_data.data))
        result = await html_to_image(html_code, img_binary_list, suggested_width, suggested_height)

        # logger.info(result)
        step = ctx.session.state['step']
        if result["status"] == "error":
            error_text = f"执行步骤{step + 1}: {self.name}执行出错：{result['message']}"
            message_for_user = f"执行步骤执行出错：{result['message']}"
            current_output = {"author": self.name, "status": "error", "message": error_text, 'message_for_user': message_for_user, 'output_text':''}

            logger.error(error_text)
            yield self.format_event(error_text, {"current_output": current_output})
            return

        else:
            text = f"执行步骤{step + 1}: {self.name}：从html转图片完成"
            message_for_user = "执行步骤从html转图片完成"
            output_artifacts = []
            html_2_image_artifacts = []

            now = datetime.datetime.now()
            time_stamp = now.strftime("%Y-%m-%d_%H-%M-%S")
            artifact_name = f"step{ctx.session.state.get('step') + 1}_pgbr_html2img_output_{time_stamp}.png"
            artifact_part = Part(inline_data=Blob(mime_type='image/png', data=result['message']))

            await ctx.artifact_service.save_artifact(
                app_name=ctx.session.app_name, user_id=ctx.session.user_id, session_id=ctx.session.id,
                filename=artifact_name, artifact=artifact_part
            )

            text += f"\nhtml2img图片保存成功，输出图片名称为{artifact_name}"
            description = f"html文件转换得到的图片。\nhtml_code：{html_code}\n"

            output_artifacts.append({'name': artifact_name, 'description': description})
            html_2_image_artifacts.append({'name': artifact_name, 'description': description})


            pgbr_image_generation_results = ctx.session.state.get('pgbr_image_generation_results', {})
            if 'output_artifacts' in pgbr_image_generation_results:
                image_list = pgbr_image_generation_results['output_artifacts']
                output_artifacts = output_artifacts + image_list

            pgbr_html_2_image_result = ctx.session.state.get('pgbr_html_2_image_result', {})
            if 'html_2_image_artifacts' in pgbr_html_2_image_result:
                image_list = pgbr_html_2_image_result['html_2_image_artifacts']
                output_artifacts = output_artifacts + image_list
                html_2_image_artifacts = html_2_image_artifacts + image_list

            current_output = {"author": self.name,
                "status": "success",
                "message": text,
                "message_for_user": message_for_user,
                "output_artifacts": output_artifacts,
                'output_text':''
            }
            yield self.format_event(text, {'current_output': current_output})


            html_2_image_result = {"html_2_image_artifacts": html_2_image_artifacts}
            yield self.format_event(text, {'pgbr_html_2_image_result': html_2_image_result})

            return








