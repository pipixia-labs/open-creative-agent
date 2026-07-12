import os

from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv()


class APIConfig(BaseModel):
    """API keys used by optional provider tools."""

    DASHSCOPE_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    SEGMIND_API_KEY: str = ""
    OPENAI_API_KEY: str = ""


API_CONFIG = APIConfig(
    DASHSCOPE_API_KEY=os.getenv("DASHSCOPE_API_KEY", ""),
    GOOGLE_API_KEY=os.getenv("GOOGLE_API_KEY", ""),
    SEGMIND_API_KEY=os.getenv("SEGMIND_API_KEY", ""),
    OPENAI_API_KEY=os.getenv("OPENAI_API_KEY", ""),
)
