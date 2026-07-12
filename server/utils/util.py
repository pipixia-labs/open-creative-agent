import base64
import datetime as dt
import json
import mimetypes
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from google.genai.types import Blob, Part
from pydantic import BaseModel

from src.logger import logger


class SessionCreateResponse(BaseModel):
    """Response payload returned by the local session creation endpoint."""

    user_id: str
    session_id: str
    message: str


def utc_now():
    """Return the current timezone-aware UTC datetime."""
    return dt.datetime.now(dt.timezone.utc)


def save_upload_file_sync(upload_file: UploadFile, uploads_dir: Path) -> str:
    """Save one uploaded file to disk and return its saved path."""
    try:
        timestamp = time.strftime("%Y%m%d%H%M%S")
        safe_filename = re.sub(r"[^\w\.\-]", "_", upload_file.filename)  # type: ignore
        file_location = os.path.join(uploads_dir, f"{timestamp}_{safe_filename}")

        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)

        logger.info(f"Uploaded file saved: {file_location}")
        return file_location
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}", exc_info=True)
        return ""
    finally:
        upload_file.file.close()


def load_file_as_part(file_path: str) -> "Part":
    """Load a local file as a Gemini Part with an inferred MIME type."""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    mime_type, _ = mimetypes.guess_type(file_path)

    if not mime_type:
        extension = path.suffix.lower()
        extra_mime_map = {
            ".json": "application/json",
            ".md": "text/markdown",
            ".csv": "text/csv",
            ".py": "text/x-python",
        }
        mime_type = extra_mime_map.get(extension, "application/octet-stream")

    with open(file_path, "rb") as f:
        file_binary = f.read()

    return Part(inline_data=Blob(mime_type=mime_type, data=file_binary))


def format_sse_event(data: dict[str, Any]) -> str:
    """Serialize a payload as one Server-Sent Events data frame."""
    json_data = json.dumps(data, ensure_ascii=False)
    return f"data: {json_data}\n\n"


def current_time_str():
    """Return a local timestamp string for debug step messages."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def encode_media(file_path: str):
    """Encode a local media file as a data URL."""
    logger.info(file_path)
    if file_path is None:
        return None

    mime_type, _ = mimetypes.guess_type(file_path)

    if mime_type is None:
        mime_type = "application/octet-stream"

    with open(file_path, "rb") as f:
        file_content = f.read()

    base64_data = base64.b64encode(file_content).decode("utf-8")
    return f"data:{mime_type};base64,{base64_data}"
