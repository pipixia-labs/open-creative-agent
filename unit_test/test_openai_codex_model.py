"""Tests for optional OpenAI Codex model support."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from src.llm.model_factory import build_model_and_config
from src.llm.openai_codex_model import CodexResponse
from src.llm.openai_codex_model import CodexToolCall
from src.llm.openai_codex_model import OpenAICodexModel
from src.llm.openai_codex_model import _consume_sse_with_reasoning
from src.llm.openai_codex_model import _convert_messages_to_responses
from src.llm.openai_codex_model import _convert_tools_to_responses
from src.llm.openai_codex_model import build_reasoning_options
from src.llm.openai_codex_model import is_openai_codex_model
from src.llm.openai_codex_model import strip_codex_model_prefix


def test_model_factory_routes_codex_models_to_codex_adapter() -> None:
    """Codex-prefixed models should bypass LiteLLM."""
    model, config = build_model_and_config("openai-codex/gpt-5.5", thinking_level="low")

    assert isinstance(model, OpenAICodexModel)
    assert model.reasoning_effort == "low"
    assert config is None


def test_model_factory_keeps_openai_api_models_on_litellm() -> None:
    """Regular OpenAI API models should continue to use LiteLLM."""
    model, config = build_model_and_config("openai/gpt-5.5", thinking_level="low")

    assert isinstance(model, LiteLlm)
    assert model.model == "openai/gpt-5.5"
    assert config is None


@pytest.mark.parametrize(
    ("model_name", "expected"),
    [
        ("openai-codex/gpt-5.5", True),
        ("openai_codex/gpt-5.5", True),
        ("openai/gpt-5.5", False),
    ],
)
def test_codex_model_detection(model_name: str, expected: bool) -> None:
    """Only Codex provider prefixes should match the Codex adapter."""
    assert is_openai_codex_model(model_name) is expected


def test_strip_codex_model_prefix() -> None:
    """The upstream request should receive the bare model id."""
    assert strip_codex_model_prefix("openai-codex/gpt-5.5") == "gpt-5.5"
    assert strip_codex_model_prefix("openai_codex/gpt-5.5") == "gpt-5.5"
    assert strip_codex_model_prefix("openai/gpt-5.5") == "openai/gpt-5.5"


def test_reasoning_options_match_nanobot_style() -> None:
    """Reasoning options should keep visible summaries enabled by default."""
    assert build_reasoning_options(None) == {"summary": "auto"}
    assert build_reasoning_options("low") == {"summary": "auto", "effort": "low"}
    assert build_reasoning_options("xhigh") == {"summary": "auto", "effort": "high"}
    assert build_reasoning_options("none") == {"effort": "none"}


def test_convert_messages_to_responses_replays_tool_calls() -> None:
    """Chat-style tool history should become Responses API input items."""
    system_prompt, input_items = _convert_messages_to_responses([
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Search"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1|fc_1",
                    "type": "function",
                    "function": {"name": "search", "arguments": "{\"query\":\"oca\"}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1|fc_1", "content": "result"},
    ])

    assert system_prompt == "You are helpful."
    assert input_items[0]["content"][0]["text"] == "Search"
    assert input_items[1]["type"] == "function_call"
    assert input_items[1]["call_id"] == "call_1"
    assert input_items[1]["id"] == "fc_1"
    assert input_items[2] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "result",
    }


def test_convert_tools_to_responses() -> None:
    """OpenAI function tool schemas should flatten for Responses API."""
    converted = _convert_tools_to_responses([
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search the web",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ])

    assert converted == [
        {
            "type": "function",
            "name": "search",
            "description": "Search the web",
            "parameters": {"type": "object", "properties": {}},
        }
    ]


def test_codex_model_generates_adk_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Codex adapter should return text, reasoning, function calls, and usage."""
    captured: dict[str, object] = {}

    def fake_get_token():
        return SimpleNamespace(account_id="acct", access="token")

    async def fake_request(url, headers, body, *, verify, timeout_s):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        captured["verify"] = verify
        captured["timeout_s"] = timeout_s
        return CodexResponse(
            content="Done",
            reasoning_content="Thinking",
            tool_calls=[
                CodexToolCall(id="call_1|fc_1", name="search", arguments={"query": "oca"})
            ],
            finish_reason="stop",
            usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        )

    monkeypatch.setattr("src.llm.openai_codex_model._get_codex_token", fake_get_token)
    monkeypatch.setattr("src.llm.openai_codex_model._request_codex", fake_request)

    model = OpenAICodexModel(model="openai-codex/gpt-5.5", reasoning_effort="low")
    request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part.from_text(text="Hello")])]
    )

    async def run_model():
        return [response async for response in model.generate_content_async(request)]

    responses = asyncio.run(run_model())

    assert captured["body"]["model"] == "gpt-5.5"
    assert captured["body"]["reasoning"] == {"summary": "auto", "effort": "low"}
    assert responses[0].content.parts[0].thought is True
    assert responses[0].content.parts[0].text == "Thinking"
    assert responses[0].content.parts[1].text == "Done"
    function_call = responses[0].content.parts[2].function_call
    assert function_call.name == "search"
    assert function_call.id == "call_1|fc_1"
    assert function_call.args == {"query": "oca"}
    assert responses[0].usage_metadata.total_token_count == 7


class _FakeSSE:
    def __init__(self, lines: list[str]):
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def test_consume_sse_with_text_reasoning_tool_and_usage() -> None:
    """The SSE parser should collect text, reasoning, tool calls, and usage."""
    response = _FakeSSE([
        'data: {"type":"response.reasoning_summary_text.delta","delta":"Plan"}',
        "",
        'data: {"type":"response.output_text.delta","delta":"Hello"}',
        "",
        (
            'data: {"type":"response.output_item.added","item":{"type":"function_call",'
            '"call_id":"call_1","id":"fc_1","name":"lookup"}}'
        ),
        "",
        (
            'data: {"type":"response.function_call_arguments.done","call_id":"call_1",'
            '"arguments":"{\\"x\\":1}"}'
        ),
        "",
        (
            'data: {"type":"response.output_item.done","item":{"type":"function_call",'
            '"call_id":"call_1","id":"fc_1","name":"lookup"}}'
        ),
        "",
        (
            'data: {"type":"response.completed","response":{"status":"completed",'
            '"usage":{"input_tokens":2,"output_tokens":3,"total_tokens":5}}}'
        ),
        "",
    ])

    parsed = asyncio.run(_consume_sse_with_reasoning(response))

    assert parsed.content == "Hello"
    assert parsed.reasoning_content == "Plan"
    assert parsed.tool_calls == [CodexToolCall(id="call_1|fc_1", name="lookup", arguments={"x": 1})]
    assert parsed.usage == {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}
