from __future__ import annotations

from typing import Any, Optional


def safe_int(value: Any) -> int:
    """Best-effort int conversion used by usage parsers."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def parse_usage_obj(obj: Any) -> Optional[dict[str, int]]:
    """Parse provider/ADK usage payload into normalized token fields."""
    if obj is None:
        return None

    usage = getattr(obj, "usage_metadata", None) or getattr(obj, "usage", None)
    if usage is None and isinstance(obj, dict):
        usage = obj.get("usage_metadata") or obj.get("usage")
    if usage is None:
        return None

    def _get(v: Any, key: str) -> Any:
        if isinstance(v, dict):
            return v.get(key)
        return getattr(v, key, None)

    prompt_tokens = safe_int(_get(usage, "prompt_token_count")) or safe_int(_get(usage, "input_tokens"))
    completion_tokens = (
        safe_int(_get(usage, "candidates_token_count"))
        or safe_int(_get(usage, "output_tokens"))
        or safe_int(_get(usage, "completion_tokens"))
    )
    total_tokens = safe_int(_get(usage, "total_token_count")) or safe_int(_get(usage, "total_tokens"))
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    if total_tokens <= 0:
        return None

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
