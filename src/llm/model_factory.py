from __future__ import annotations

from typing import Any, Optional

from google.adk.models.google_llm import Gemini
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from conf.system import SYS_CONFIG


def is_gemini_model(model_name: str) -> bool:
    """Return True when model string points to Gemini family."""
    value = (model_name or "").lower().strip()
    return "gemini" in value


def is_openai_model(model_name: str) -> bool:
    """Return True when model string points to OpenAI family."""
    value = (model_name or "").lower().strip()
    return (
        value.startswith("openai/")
        or "gpt-" in value
        or value.startswith("o1")
        or value.startswith("o3")
    )


def normalize_gemini_model_name(model_name: str) -> str:
    """Convert LiteLLM Gemini model names to native Gemini model names."""
    value = (model_name or "").strip()
    if value.lower().startswith("gemini/"):
        return value.split("/", 1)[1]
    return value


def normalize_thinking_level(level: str) -> str:
    """Normalize configured thinking level to the supported unified value."""
    value = (level or "").strip().lower()
    if value in {"low", "medium", "high", "xhigh"}:
        return value
    return "medium"


def gemini_thinking_level(level: str) -> str:
    """Map unified thinking level to Gemini-supported level."""
    normalized = normalize_thinking_level(level)
    if normalized == "xhigh":
        return "high"
    return normalized


def openai_reasoning_effort(level: str) -> str:
    """Map unified thinking level to OpenAI reasoning effort."""
    value = (level or "").strip().lower()
    if value in {"none", "low", "medium", "high", "xhigh"}:
        return value
    return "medium"


def build_model_and_config(
    model_name: str,
    thinking_level: Optional[str] = None,
) -> tuple[Any, Optional[types.GenerateContentConfig]]:
    """
    Build ADK model instance and optional generate_content_config.

    Rules:
    - Gemini family: use native Gemini adapter with unified thinking level.
    - Non-Gemini family: use LiteLlm.
    - OpenAI family: map unified thinking level to reasoning_effort.
    """
    effective_thinking_level = thinking_level or SYS_CONFIG.thinking_level

    if is_gemini_model(model_name):
        gemini_model = Gemini(model=normalize_gemini_model_name(model_name))
        generate_content_config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_level=gemini_thinking_level(effective_thinking_level)
            )
        )
        return gemini_model, generate_content_config

    kwargs: dict[str, Any] = {}
    if is_openai_model(model_name):
        kwargs["reasoning_effort"] = openai_reasoning_effort(effective_thinking_level)
    return LiteLlm(model=model_name, **kwargs), None
