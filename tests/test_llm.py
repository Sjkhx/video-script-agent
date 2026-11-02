import json
from types import SimpleNamespace

import httpx
import openai
import pytest
from openai.types.chat import ChatCompletion

from script_agent.llm import LLMError, OpenAICompatibleLLM, ScriptedLLM


def completion(message):
    return ChatCompletion.model_validate({
        "id": "c1", "object": "chat.completion", "created": 1, "model": "m",
        "choices": [{"index": 0, "finish_reason": "tool_calls", "message": message}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    })


class StubClient:
    def __init__(self, response=None, error=None):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.response, self.error, self.kwargs = response, error, None
    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def test_parses_tool_calls_and_keeps_provider_fields():
    message = {"role": "assistant", "content": None, "reasoning_content": "内部推理", "tool_calls": [
        {"id": "a", "type": "function", "function": {"name": "search_materials", "arguments": "{\"query\":\"字幕\"}"}},
    ]}
    client = StubClient(completion(message))
    resp = OpenAICompatibleLLM("m", client=client).complete([{"role": "user", "content": "x"}], [])
    assert resp.tool_calls[0].name == "search_materials"
    assert resp.tool_calls[0].arguments == "{\"query\":\"字幕\"}"
    assert resp.raw_message["reasoning_content"] == "内部推理"
    assert resp.usage["prompt_tokens"] == 3
    assert client.kwargs["model"] == "m"


def test_client_sends_tools_and_tool_choice():
    client = StubClient(completion({"role": "assistant", "content": "你好"}))
    tools = [{"type": "function", "function": {"name": "search_materials"}}]
    OpenAICompatibleLLM("m", client=client).complete([{"role": "user", "content": "x"}], tools)
    assert client.kwargs["tools"] == tools
    assert client.kwargs["tool_choice"] == "auto"


def test_usage_object_is_normalized_to_plain_dict():
    client = StubClient(completion({"role": "assistant", "content": "你好"}))
    resp = OpenAICompatibleLLM("m", client=client).complete([], [])
    assert isinstance(resp.usage, dict)
    assert resp.usage["total_tokens"] == 5


def test_raw_message_keeps_tool_call_shape():
    message = {"role": "assistant", "content": None, "tool_calls": [
        {"id": "a", "type": "function", "function": {"name": "search_materials", "arguments": "{}"}},
    ]}
    resp = OpenAICompatibleLLM("m", client=StubClient(completion(message))).complete([], [])
    assert resp.raw_message["role"] == "assistant"
    assert resp.raw_message["tool_calls"] == [
        {"id": "a", "type": "function", "function": {"name": "search_materials", "arguments": "{}"}},
    ]


def test_api_error_becomes_llm_error():
    client = StubClient(error=openai.APIConnectionError(request=httpx.Request("POST", "http://x")))
    with pytest.raises(LLMError):
        OpenAICompatibleLLM("m", client=client).complete([], [])


def test_api_error_does_not_leak_key():
    key = "sk-test-should-not-leak"
    error = openai.APIConnectionError(request=httpx.Request("POST", "http://x"), message=f"failed with {key}")
    client = StubClient(error=error)
    with pytest.raises(LLMError) as excinfo:
        OpenAICompatibleLLM("m", api_key=key, client=client).complete([], [])
    assert key not in str(excinfo.value)


def test_scripted_llm_modes():
    llm = ScriptedLLM([
        {"tool_calls": [{"name": "search_materials", "arguments": {"query": "字幕"}}]},
        {"tool_calls": [{"name": "search_materials", "arguments": "{bad"}]},
        {"content": "你好"},
        {"raise": "boom"},
    ])
    first = llm.complete([{"role": "user", "content": "x"}], [])
    assert json.loads(first.tool_calls[0].arguments) == {"query": "字幕"}
    assert first.raw_message["role"] == "assistant" and first.raw_message["tool_calls"][0]["id"] == first.tool_calls[0].id
    assert llm.complete([], []).tool_calls[0].arguments == "{bad"
    assert llm.complete([], []).content == "你好"
    with pytest.raises(LLMError, match="boom"):
        llm.complete([], [])
    with pytest.raises(LLMError):
        llm.complete([], [])
    assert llm.seen_messages[0] == [{"role": "user", "content": "x"}]


def test_scripted_llm_ids_are_sequential_across_steps():
    llm = ScriptedLLM([
        {"tool_calls": [{"name": "a", "arguments": {}}, {"name": "b", "arguments": "{}"}]},
        {"tool_calls": [{"name": "c", "arguments": {}}]},
    ])
    first, second = llm.complete([], []), llm.complete([], [])
    assert [c.id for c in first.tool_calls] == ["call_1", "call_2"]
    assert second.tool_calls[0].id == "call_3"
    assert [c["id"] for c in first.raw_message["tool_calls"]] == ["call_1", "call_2"]


def test_scripted_llm_usage_is_zero_and_seen_messages_are_copies():
    llm = ScriptedLLM([{"content": "ok"}])
    messages = [{"role": "user", "content": "x"}]
    resp = llm.complete(messages, [])
    messages.append({"role": "user", "content": "later"})
    assert llm.seen_messages[0] == [{"role": "user", "content": "x"}]
    assert resp.usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def test_scripted_llm_from_file(tmp_path):
    path = tmp_path / "script.json"
    path.write_text(json.dumps({"steps": [{"tool_calls": [{"name": "search_materials", "arguments": {"query": "字幕"}}]}]}, ensure_ascii=False), encoding="utf-8")
    resp = ScriptedLLM.from_file(path).complete([], [])
    assert resp.tool_calls[0].name == "search_materials"
    assert json.loads(resp.tool_calls[0].arguments) == {"query": "字幕"}


def test_scripted_llm_unknown_step_is_llm_error():
    with pytest.raises(LLMError):
        ScriptedLLM([{"nothing": True}]).complete([], [])
