from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Optional

import httpx
from google.adk.models.base_llm import BaseLlm
from google.adk.models.lite_llm import _append_fallback_user_content_if_missing
from google.adk.models.lite_llm import _get_completion_inputs
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from src.logger import logger


DEFAULT_CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"
DEFAULT_ORIGINATOR = "open-creative-agent"
DEFAULT_TIMEOUT_S = 90.0


@dataclass(frozen=True)
class CodexToolCall:
    """Function call parsed from the Codex Responses API stream."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class CodexResponse:
    """Normalized Codex response used by the ADK adapter."""

    content: str
    tool_calls: list[CodexToolCall]
    finish_reason: str
    usage: dict[str, int]
    reasoning_content: Optional[str] = None


class OpenAICodexModel(BaseLlm):
    """ADK model adapter for OpenAI Codex OAuth Responses API."""

    reasoning_effort: Optional[str] = None
    timeout_s: float = DEFAULT_TIMEOUT_S

    @classmethod
    def supported_models(cls) -> list[str]:
        """Return supported OpenAI Codex model patterns."""
        return [r"openai-codex/.*", r"openai_codex/.*"]

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """Generate one ADK model turn through the Codex Responses API."""
        _ = stream
        self._maybe_append_user_content(llm_request)
        _append_fallback_user_content_if_missing(llm_request)

        effective_model = llm_request.model or self.model
        conversion_model = _as_openai_conversion_model(effective_model)
        messages, tools, _response_format, generation_params = await _get_completion_inputs(
            llm_request,
            conversion_model,
        )

        try:
            response = await self._call_codex(
                model=effective_model,
                messages=[_plain_dict(message) for message in messages],
                tools=[_plain_dict(tool) for tool in tools] if tools else None,
                generation_params=generation_params or {},
            )
        except Exception as exc:
            logger.warning(
                "Codex model request failed: type={} summary={}",
                type(exc).__name__,
                _safe_log_detail(exc),
            )
            yield _error_response(effective_model, exc)
            return

        yield _to_adk_response(effective_model, response)

    async def _call_codex(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]],
        generation_params: dict[str, Any],
    ) -> CodexResponse:
        """Build and send the Codex Responses API request."""
        system_prompt, input_items = _convert_messages_to_responses(messages)
        token = await asyncio.to_thread(_get_codex_token)
        headers = _build_headers(token.account_id, token.access)

        body: dict[str, Any] = {
            "model": strip_codex_model_prefix(model),
            "store": False,
            "stream": True,
            "instructions": system_prompt,
            "input": input_items,
            "text": {"verbosity": "medium"},
            "include": ["reasoning.encrypted_content"],
            "prompt_cache_key": _prompt_cache_key(messages[:2]),
            "tool_choice": "auto",
            "parallel_tool_calls": True,
        }
        max_output_tokens = generation_params.get("max_completion_tokens")
        if max_output_tokens:
            body["max_output_tokens"] = max_output_tokens

        reasoning_options = build_reasoning_options(self.reasoning_effort)
        if reasoning_options:
            body["reasoning"] = reasoning_options
        if tools:
            body["tools"] = _convert_tools_to_responses(tools)

        try:
            return await _request_codex(
                DEFAULT_CODEX_URL,
                headers,
                body,
                verify=True,
                timeout_s=self.timeout_s,
            )
        except Exception as exc:
            if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
                raise
            logger.warning("SSL verification failed for Codex API; retrying with verify=False")
            return await _request_codex(
                DEFAULT_CODEX_URL,
                headers,
                body,
                verify=False,
                timeout_s=self.timeout_s,
            )


def is_openai_codex_model(model_name: str) -> bool:
    """Return True when the model string targets the Codex OAuth provider."""
    value = (model_name or "").lower().strip()
    return value.startswith("openai-codex/") or value.startswith("openai_codex/")


def strip_codex_model_prefix(model_name: str) -> str:
    """Strip the local Codex provider prefix before sending the upstream model."""
    value = (model_name or "").strip()
    if "/" in value and is_openai_codex_model(value):
        return value.split("/", 1)[1]
    return value


def build_reasoning_options(reasoning_effort: Optional[str]) -> Optional[dict[str, str]]:
    """Build Codex Responses API reasoning options."""
    if not reasoning_effort:
        return {"summary": "auto"}
    effort = reasoning_effort.lower().strip()
    if effort == "none":
        return {"effort": "none"}
    if effort == "xhigh":
        effort = "high"
    return {"summary": "auto", "effort": effort}


def _as_openai_conversion_model(model_name: str) -> str:
    """Return an OpenAI-compatible model string for ADK message conversion."""
    if is_openai_codex_model(model_name):
        return f"openai/{strip_codex_model_prefix(model_name)}"
    return model_name


def _get_codex_token():
    """Return the locally stored Codex OAuth token."""
    try:
        from oauth_cli_kit import get_token
    except ImportError as exc:
        raise RuntimeError(
            "oauth-cli-kit is not installed. Install dependencies or run scripts/start_local.sh."
        ) from exc

    token = get_token()
    if not token or not getattr(token, "access", None):
        raise RuntimeError("Codex OAuth token is unavailable. Run scripts/login_codex.py first.")
    return token


def _build_headers(account_id: str, token: str) -> dict[str, str]:
    """Build HTTP headers required by the Codex backend."""
    return {
        "Authorization": f"Bearer {token}",
        "chatgpt-account-id": account_id,
        "OpenAI-Beta": "responses=experimental",
        "originator": DEFAULT_ORIGINATOR,
        "User-Agent": "open-creative-agent (python)",
        "accept": "text/event-stream",
        "content-type": "application/json",
    }


async def _request_codex(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    *,
    verify: bool,
    timeout_s: float,
) -> CodexResponse:
    """Request Codex and parse the SSE response stream."""
    async with httpx.AsyncClient(timeout=timeout_s, verify=verify) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            if response.status_code != 200:
                raw = (await response.aread()).decode("utf-8", "ignore")
                raise CodexHTTPError(
                    _friendly_http_error(response.status_code),
                    status_code=response.status_code,
                    error_type=_extract_error_field(raw, "type"),
                    error_code=_extract_error_field(raw, "code"),
                )
            return await _consume_sse_with_reasoning(response)


class CodexHTTPError(RuntimeError):
    """HTTP error returned by the Codex backend."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        error_type: Optional[str] = None,
        error_code: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
        self.error_code = error_code


async def _consume_sse_with_reasoning(response: httpx.Response) -> CodexResponse:
    """Consume a Codex Responses API SSE stream."""
    content = ""
    tool_calls: list[CodexToolCall] = []
    tool_call_buffers: dict[str, dict[str, Any]] = {}
    finish_reason = "stop"
    usage: dict[str, int] = {}
    reasoning_content: Optional[str] = None
    streamed_reasoning = False

    async for event in _iter_sse(response):
        event_type = event.get("type")
        if event_type == "response.output_item.added":
            item = event.get("item") or {}
            if item.get("type") == "function_call" and item.get("call_id"):
                call_id = str(item["call_id"])
                tool_call_buffers[call_id] = {
                    "id": item.get("id") or "fc_0",
                    "name": item.get("name") or "",
                    "arguments": item.get("arguments") or "",
                }
        elif event_type == "response.output_text.delta":
            content += event.get("delta") or ""
        elif event_type == "response.reasoning_summary_text.delta":
            delta_text = event.get("delta") or ""
            if delta_text:
                reasoning_content = (reasoning_content or "") + delta_text
                streamed_reasoning = True
        elif event_type == "response.reasoning_summary_text.done":
            text = event.get("text") or ""
            if text and not streamed_reasoning and not reasoning_content:
                reasoning_content = text
        elif event_type == "response.reasoning_summary_part.done":
            part = event.get("part") or {}
            text = part.get("text") if part.get("type") == "summary_text" else None
            if text and not streamed_reasoning and not reasoning_content:
                reasoning_content = text
        elif event_type == "response.function_call_arguments.delta":
            call_id = str(event.get("call_id") or "")
            if call_id in tool_call_buffers:
                tool_call_buffers[call_id]["arguments"] += event.get("delta") or ""
        elif event_type == "response.function_call_arguments.done":
            call_id = str(event.get("call_id") or "")
            if call_id in tool_call_buffers:
                tool_call_buffers[call_id]["arguments"] = event.get("arguments") or ""
        elif event_type == "response.output_item.done":
            item = event.get("item") or {}
            if item.get("type") == "function_call" and item.get("call_id"):
                call_id = str(item["call_id"])
                buffer = tool_call_buffers.get(call_id) or {}
                raw_args = _first_non_empty(buffer.get("arguments"), item.get("arguments"), "{}")
                item_id = buffer.get("id") or item.get("id") or "fc_0"
                tool_calls.append(
                    CodexToolCall(
                        id=f"{call_id}|{item_id}",
                        name=buffer.get("name") or item.get("name") or "",
                        arguments=_parse_tool_arguments(raw_args),
                    )
                )
            elif item.get("type") == "reasoning" and not reasoning_content:
                reasoning_content = _extract_reasoning_summary([item])
        elif event_type == "response.completed":
            response_obj = event.get("response") or {}
            finish_reason = _map_response_status(response_obj.get("status"))
            usage = _usage_from_response(response_obj) or usage
            if not reasoning_content:
                reasoning_content = _extract_reasoning_summary(response_obj.get("output") or [])
        elif event_type in {"error", "response.failed"}:
            detail = event.get("error") or event.get("message") or event
            raise RuntimeError(f"Codex response failed: {str(detail)[:500]}")

    return CodexResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        usage=usage,
        reasoning_content=reasoning_content,
    )


async def _iter_sse(response: httpx.Response) -> AsyncGenerator[dict[str, Any], None]:
    """Yield parsed JSON objects from an SSE response."""
    buffer: list[str] = []

    async for line in response.aiter_lines():
        if line == "":
            event = _flush_sse_buffer(buffer)
            if event is not None:
                yield event
            continue
        buffer.append(line)

    event = _flush_sse_buffer(buffer)
    if event is not None:
        yield event


def _flush_sse_buffer(buffer: list[str]) -> Optional[dict[str, Any]]:
    """Parse and clear one buffered SSE event."""
    data_lines = [line[5:].strip() for line in buffer if line.startswith("data:")]
    buffer.clear()
    if not data_lines:
        return None
    data = "\n".join(data_lines).strip()
    if not data or data == "[DONE]":
        return None
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        logger.warning("Failed to parse Codex SSE event JSON: {}", data[:200])
        return None
    return parsed if isinstance(parsed, dict) else None


def _convert_messages_to_responses(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Convert Chat Completions messages to Responses API input items."""
    system_parts: list[str] = []
    input_items: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for idx, message in enumerate(messages):
        role = message.get("role")
        content = message.get("content")

        if role == "system":
            if isinstance(content, str) and content:
                system_parts.append(content)
            continue
        if role == "user":
            input_items.append(_convert_user_message(content))
            continue
        if role == "assistant":
            if isinstance(content, str) and content:
                input_items.append({
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": content}],
                    "status": "completed",
                    "id": _unique_item_id(f"msg_{idx}", used_ids),
                })
            for tool_call in message.get("tool_calls") or []:
                function = tool_call.get("function") or {}
                call_id, item_id = _split_tool_call_id(tool_call.get("id"))
                input_items.append({
                    "type": "function_call",
                    "id": _unique_item_id(item_id or f"fc_{idx}", used_ids),
                    "call_id": call_id or f"call_{idx}",
                    "name": function.get("name") or "",
                    "arguments": _json_string(function.get("arguments") or "{}"),
                })
            continue
        if role in {"tool", "tool_responses"}:
            call_id, _item_id = _split_tool_call_id(message.get("tool_call_id"))
            input_items.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": _json_string(content),
            })

    return "\n\n".join(system_parts), input_items


def _convert_user_message(content: Any) -> dict[str, Any]:
    """Convert one user message to a Responses API message item."""
    if isinstance(content, str):
        return {"role": "user", "content": [{"type": "input_text", "text": content}]}
    converted: list[dict[str, Any]] = []
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                converted.append({"type": "input_text", "text": item.get("text") or ""})
            elif item.get("type") == "image_url":
                url = (item.get("image_url") or {}).get("url")
                if url:
                    converted.append({"type": "input_image", "image_url": url, "detail": "auto"})
    if not converted:
        converted.append({"type": "input_text", "text": ""})
    return {"role": "user", "content": converted}


def _convert_tools_to_responses(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert OpenAI-style function tools to Responses API function tools."""
    converted: list[dict[str, Any]] = []
    for tool in tools:
        function = tool.get("function") if tool.get("type") == "function" else tool
        if not isinstance(function, dict) or not function.get("name"):
            continue
        parameters = function.get("parameters") or {}
        converted.append({
            "type": "function",
            "name": function["name"],
            "description": function.get("description") or "",
            "parameters": parameters if isinstance(parameters, dict) else {},
        })
    return converted


def _to_adk_response(model: str, response: CodexResponse) -> LlmResponse:
    """Convert a normalized Codex response into an ADK LlmResponse."""
    parts: list[types.Part] = []
    if response.reasoning_content:
        reasoning_part = types.Part.from_text(text=response.reasoning_content)
        reasoning_part.thought = True
        parts.append(reasoning_part)
    if response.content:
        parts.append(types.Part.from_text(text=response.content))
    for tool_call in response.tool_calls:
        part = types.Part.from_function_call(name=tool_call.name, args=tool_call.arguments)
        part.function_call.id = tool_call.id
        parts.append(part)

    finish_reason = _map_finish_reason(response.finish_reason)
    llm_response = LlmResponse(
        content=types.Content(role="model", parts=parts),
        finish_reason=finish_reason,
        model_version=model,
    )
    if response.usage:
        llm_response.usage_metadata = types.GenerateContentResponseUsageMetadata(
            prompt_token_count=response.usage.get("prompt_tokens", 0),
            candidates_token_count=response.usage.get("completion_tokens", 0),
            total_token_count=response.usage.get("total_tokens", 0),
        )
    if finish_reason != types.FinishReason.STOP:
        llm_response.error_code = finish_reason
        llm_response.error_message = f"Finished with {finish_reason.name}"
    return llm_response


def _error_response(model: str, exc: Exception) -> LlmResponse:
    """Convert provider errors into an ADK error response."""
    message = f"Error calling Codex ({type(exc).__name__}): {str(exc) or 'unexpected error'}"
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part.from_text(text=message)]),
        error_code="openai_codex_error",
        error_message=message,
        finish_reason=types.FinishReason.OTHER,
        model_version=model,
    )


def _map_response_status(status: Optional[str]) -> str:
    """Map Responses API status to a compact finish reason."""
    if status == "incomplete":
        return "length"
    if status in {"failed", "cancelled"}:
        return "error"
    return "stop"


def _map_finish_reason(finish_reason: str) -> types.FinishReason:
    """Map compact finish reason to google-genai FinishReason."""
    if finish_reason == "length":
        return types.FinishReason.MAX_TOKENS
    if finish_reason in {"stop", "tool_calls", "function_call"}:
        return types.FinishReason.STOP
    return types.FinishReason.OTHER


def _usage_from_response(response: dict[str, Any]) -> dict[str, int]:
    """Extract token usage from a Responses API response object."""
    usage = response.get("usage") or {}
    if not isinstance(usage, dict):
        return {}
    prompt_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _extract_reasoning_summary(output: Any) -> Optional[str]:
    """Extract reasoning summary text from Responses API output items."""
    parts: list[str] = []
    for item in output or []:
        if not isinstance(item, dict) or item.get("type") != "reasoning":
            continue
        for summary in item.get("summary") or []:
            if isinstance(summary, dict) and summary.get("type") == "summary_text":
                text = summary.get("text")
                if text:
                    parts.append(text)
    return "".join(parts) or None


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    """Parse function-call arguments into a dictionary."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            logger.warning("Failed to parse Codex tool arguments: {}", raw[:200])
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _json_string(value: Any) -> str:
    """Serialize arbitrary values for Responses API replay fields."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _first_non_empty(*values: Any) -> Any:
    """Return the first value that is not empty."""
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return "{}"


def _unique_item_id(item_id: str, used: set[str]) -> str:
    """Return an item id unique within a Responses API request."""
    if item_id not in used:
        used.add(item_id)
        return item_id
    suffix = 2
    while f"{item_id}_{suffix}" in used:
        suffix += 1
    unique = f"{item_id}_{suffix}"
    used.add(unique)
    return unique


def _split_tool_call_id(tool_call_id: Any) -> tuple[str, Optional[str]]:
    """Split a compound `call_id|item_id` value."""
    if isinstance(tool_call_id, str) and tool_call_id:
        if "|" in tool_call_id:
            call_id, item_id = tool_call_id.split("|", 1)
            return call_id, item_id or None
        return tool_call_id, None
    return "call_0", None


def _prompt_cache_key(messages: list[dict[str, Any]]) -> str:
    """Build a stable prompt cache key for the first conversation items."""
    raw = json.dumps(messages, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _plain_dict(value: Any) -> dict[str, Any]:
    """Convert TypedDict-like or Pydantic-like values into plain dictionaries."""
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    return dict(value)


def _friendly_http_error(status_code: int) -> str:
    """Return a sanitized Codex HTTP error message."""
    if status_code == 429:
        return "ChatGPT usage quota exceeded or rate limit triggered. Please try again later."
    return f"HTTP {status_code}: Codex API request failed"


def _extract_error_field(raw: str, field: str) -> Optional[str]:
    """Extract an OpenAI-style error field from a raw JSON response."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    error = parsed.get("error") if isinstance(parsed, dict) else None
    if isinstance(error, dict):
        value = error.get(field)
        return str(value) if value else None
    return None


def _safe_log_detail(exc: Exception) -> str:
    """Return bounded diagnostic text without request payloads."""
    if isinstance(exc, CodexHTTPError):
        parts = [f"status={exc.status_code}"]
        if exc.error_type:
            parts.append(f"type={exc.error_type}")
        if exc.error_code:
            parts.append(f"code={exc.error_code}")
        return " ".join(parts)
    return type(exc).__name__
