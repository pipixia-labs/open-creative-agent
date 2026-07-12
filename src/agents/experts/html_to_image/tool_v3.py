import asyncio
import os
import os.path
import tempfile
from pathlib import Path
from playwright.async_api import async_playwright
from src.logger import logger

# html = Path(r"test/haibao2.html")
# OUT_DIR = Path(r"./shots")
# OUT_DIR.mkdir(exist_ok=True)

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
        logger.info(td)
        html_file_path = os.path.join(td, "index.html")
        with open(html_file_path, "w", encoding="utf-8") as fh:
            fh.write(html_code)

        for img_name, img_bin in img_binary_list:
            # safe_name = os.path.basename(img_name)
            save_name = os.path.join(td, img_name)
            folder_path = os.path.dirname(save_name)
            os.makedirs(folder_path, exist_ok=True)
            with open(save_name, "wb") as fh:
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

# async def main():
#     with open(html, 'r', encoding="utf-8") as f:
#         html_code = f.read()
#     result = await html_to_image(html_code, [])
#     # print(result)
#     if result['status'] == 'success':
#         with open(os.path.join(OUT_DIR, 'result.png'), 'wb') as f:
#             f.write(result['message'])
# if __name__ == "__main__":
#     asyncio.run(main())