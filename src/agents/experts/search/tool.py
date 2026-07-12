import asyncio
import os
import json
import httpx
from typing import Any
from urllib.parse import urlparse, unquote
from pathlib import PurePosixPath
from http import HTTPStatus
import requests
from bs4 import BeautifulSoup
import trafilatura
from tavily import TavilyClient
from tavily import AsyncTavilyClient

from dashscope import ImageSynthesis
from google.adk.tools import ToolContext
from google.adk.events import Event, EventActions
from google.genai.types import Part
from google.genai.types import Content
from asyncddgs import aDDGS

from conf.system import SYS_CONFIG
from conf.api import API_CONFIG
from src.logger import logger


# def get_text_from_url(url: str) -> str:
#     """
#     Input a URL and return all visible text content from that web page.
#     """
#     try:
#         # Send the HTTP request
#         response = requests.get(url, timeout=10)
#         response.raise_for_status()  # Check if the request was successful
#         # Parse the HTML content with BeautifulSoup
#         soup = BeautifulSoup(response.text, 'html.parser')
#         # Remove script and style elements
#         for script_or_style in soup(['script', 'style']):
#             script_or_style.decompose()
#         # Extract text
#         text = soup.get_text(separator='\n')
#         # Clean up extra whitespace and empty lines
#         cleaned_text = '\n'.join(line.strip() for line in text.splitlines() if line.strip())
#         return cleaned_text
#     except requests.RequestException as e:
#         return f"Error fetching the web page: {e}"
#     except Exception as e:
#         return f"Error parsing the web page: {e}"

async def retrieve_image_by_text(tool_context: ToolContext) ->  dict[str, Any]:
    """
    Retrieves images based on a text query.
    """
    current_parameters = tool_context.state.get("current_parameters",{})

    query = current_parameters.get("query")
    count = current_parameters.get("count", 5)

    logger.info(f"[{retrieve_image_by_text}] called,query={query},count={count}")

    SERPER_API_KEY = os.getenv("SERPER_API_KEY")
    if not SERPER_API_KEY:
        logger.error("Serper API key is not set.")
        state_changes = {
            "status": "error",
            "error_message": "Serper API key is not set."
        }
        return state_changes

    url = "https://google.serper.dev/images"
    payload = json.dumps({"q": f"{query}"})
    headers = {
        "X-API-KEY": f"{SERPER_API_KEY}",
        "Content-Type": "application/json",
    }
    #response = requests.request("POST", url, headers=headers, data=payload)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, data=payload, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            return {
                "status": "error",
                "message": f"HTTP error: {e.response.status_code} {e.response.reason_phrase}"
            }
        except httpx.RequestError as e:
            return {
                "status": "error",
                "message": f"Request failed: {str(e)}"
            }

    response_json = response.json()
    if "images" not in response_json:
        return {
            "status": "error",
            "message": "Search succeeded , but No images found."
        }

    url_list = [image['imageUrl'] for image in response_json["images"][:count]]
    content_list = []

    tasks = [download_image(url) for url in url_list]
    result_list = await asyncio.gather(*tasks)
    content_list = []
    for result in result_list:
        if result: content_list.append(result)
    
    if len(content_list)==0:
        return {
            "status": "error",
            "message": f"已获取{count}张图片的url，但是全部下载失败"
        }
    else:
        return {
            "status": "success",
            "message": content_list
        }

async def download_image(image_url) -> str:
    logger.info(f"downloading image,image_url={image_url}")

    try:
        async with httpx.AsyncClient() as client:

        #response = requests.get(image_url)
            response = await client.get(url=image_url)
            response.raise_for_status()

            if not response.headers.get("Content-Type", "").startswith('image/'):
                logger.error(f"Failed to download image {image_url}: invalid content type")
                return None

        # Convert to PNG format using PIL
        from PIL import Image
        from io import BytesIO

        # Open the image from response content
        image = Image.open(BytesIO(response.content))
        # Convert to RGB if necessary (for PNG compatibility)
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
        else:
            image = image.convert("RGB")

        output_buffer = BytesIO()
        image.save(output_buffer, format='PNG')
        binary_data = output_buffer.getvalue()
        logger.info(f"Downloaded image successfully: {image_url}")

        return binary_data
    except Exception as e:
        logger.error(f"Failed to download image {image_url}: {str(e)}")
        return None

def get_text_from_url(url: str):
    downloaded = trafilatura.fetch_url(url)
    return trafilatura.extract(downloaded) if downloaded else None

async def DDGS_search(tool_context: ToolContext) -> dict[str, Any]:
    current_parameters = tool_context.state.get("current_parameters",{})
    query = current_parameters.get("query")

    try:
        async with aDDGS() as ddgs:
            result = await ddgs.text(
                keywords=query,
                region='wt-wt', # world wide
                max_results=10,
                timelimit='y'
            )

            for i, item in enumerate(result):
                url = item.get('href', 'no_url')
                text_content = ''
                if 'no_url' not in url:
                    text_content = get_text_from_url(url)
                    if text_content is not None and len(text_content) > 30 and not text_content.startswith('Error'):
                        result[i]['body'] = text_content
                # else:
            
            return {
                "status": "success",
                "message": result
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"duckduckgo-search error: {str(e)}"
        }

async def tavily_search(tool_context: ToolContext) -> dict[str, Any]:
    current_parameters = tool_context.state.get("current_parameters",{})
    query = current_parameters.get("query")
    result_list = []
    query_list = query.split(';')
    try:
        for q in query_list:
            tavily_client = TavilyClient()
            # tavily_client = AsyncTavilyClient()
            response =  tavily_client.search(query=q, include_raw_content=True)
            # print(response)
            if response is not None:
                result = response['results']  # url、title、content
                result_list.extend(result)

    except Exception as e:
        return {
            "status": "error",
            "message": f"tavily-search error: {str(e)}"
        }
    return {
        "status": "success",
        "message": result_list
    }
