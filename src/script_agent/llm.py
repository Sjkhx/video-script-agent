"""模型客户端：OpenAI 兼容实现与离线脚本实现，二者共用同一个协议。"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import openai

_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9._\-]{4,}")


class LLMError(Exception):
    """模型调用失败；错误信息里不会出现密钥。"""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # 原始 JSON 字符串，由调用方决定怎么解析


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall]
    raw_message: dict
    usage: dict


class LLMClient(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        ...


def _as_plain_dict(value: Any) -> dict:
    """把 SDK 的 pydantic 对象或映射统一成普通 dict。"""
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        try:
            return dict(value.model_dump(exclude_none=True))
        except TypeError:
            return dict(value.model_dump())
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}


def _redact(text: str, secret: str | None) -> str:
    if secret:
        text = text.replace(secret, "***")
    return _KEY_PATTERN.sub("sk-***", text)


def _raw_arguments(arguments: Any) -> str:
    """arguments 一律保存为原始 JSON 字符串；已经是字符串就原样保留。"""
    if isinstance(arguments, str):
        return arguments
    return json.dumps(arguments if arguments is not None else {}, ensure_ascii=False)


def _copy_messages(messages: Any) -> list[dict]:
    """记录调用方当时发来的消息副本，后续追加或修改不会影响记录。"""
    if not isinstance(messages, list):
        return []
    return [copy.deepcopy(message) for message in messages]


class OpenAICompatibleLLM:
    """调用 OpenAI 兼容接口的 chat.completions；任何 SDK 错误都转成 LLMError。"""

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        client: Any = None,
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self._api_key = api_key
        if client is not None:
            self._client = client
        else:
            try:
                self._client = openai.OpenAI(
                    api_key=api_key,
                    base_url=base_url or None,
                    timeout=timeout,
                    max_retries=2,
                )
            except openai.OpenAIError as exc:
                # 初始化失败也要统一成 LLMError，且不能带出密钥。
                raise LLMError(
                    f"模型客户端初始化失败："
                    f"{_redact(str(exc), self._api_key) or type(exc).__name__}"
                ) from exc

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        try:
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
            message = completion.choices[0].message
        except openai.OpenAIError as exc:
            raise LLMError(
                f"模型调用失败：{_redact(str(exc), self._api_key) or type(exc).__name__}"
            ) from exc
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            raise LLMError(
                f"模型返回格式异常：{_redact(str(exc), self._api_key) or type(exc).__name__}"
            ) from exc
        if message is None:
            raise LLMError("模型返回格式异常：响应里没有 message。")

        tool_calls: list[ToolCall] = []
        raw_tool_calls = getattr(message, "tool_calls", None) or []
        for item in raw_tool_calls:
            function = getattr(item, "function", None)
            tool_calls.append(
                ToolCall(
                    id=str(getattr(item, "id", "") or ""),
                    name=str(getattr(function, "name", "") or ""),
                    arguments=str(getattr(function, "arguments", "") or ""),
                )
            )

        # exclude_none 保留厂商附加字段（如 reasoning_content），也不改动 tool_calls 形状。
        raw_message = _as_plain_dict(message)
        usage = _as_plain_dict(getattr(completion, "usage", None))
        return LLMResponse(
            content=getattr(message, "content", None),
            tool_calls=tool_calls,
            raw_message=raw_message,
            usage=usage,
        )


class ScriptedLLM:
    """离线脚本模型：按预设步骤返回，只用于验证流程。"""

    def __init__(self, steps: list[dict]) -> None:
        self._steps = list(steps)
        self._index = 0
        self._call_count = 0
        self.seen_messages: list[list[dict]] = []

    @classmethod
    def from_file(cls, path: Path) -> "ScriptedLLM":
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise LLMError(f"读取预设脚本失败：{path}（{exc}）") from exc
        steps = payload.get("steps") if isinstance(payload, dict) else None
        if not isinstance(steps, list):
            raise LLMError(f"脚本文件缺少 steps 列表：{path}")
        return cls(steps)

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        self.seen_messages.append(_copy_messages(messages))
        if self._index >= len(self._steps):
            raise LLMError(
                f"预设脚本已用完（共 {len(self._steps)} 步），模型无法继续决策。"
            )
        step = self._steps[self._index]
        self._index += 1

        if not isinstance(step, dict):
            raise LLMError(f"预设脚本第 {self._index} 步不是 JSON 对象。")
        if "raise" in step:
            raise LLMError(str(step["raise"]))

        if "tool_calls" in step:
            return self._tool_call_response(step["tool_calls"])
        if "content" in step:
            content = step["content"]
            return LLMResponse(
                content=None if content is None else str(content),
                tool_calls=[],
                raw_message={"role": "assistant", "content": content},
                usage=self._zero_usage(),
            )
        raise LLMError(f"预设脚本第 {self._index} 步缺少 tool_calls 或 content。")

    def _tool_call_response(self, specs: Any) -> LLMResponse:
        if not isinstance(specs, list) or not specs:
            raise LLMError(f"预设脚本第 {self._index} 步的 tool_calls 必须是非空列表。")
        raw_calls: list[dict] = []
        calls: list[ToolCall] = []
        for spec in specs:
            if not isinstance(spec, dict) or not spec.get("name"):
                raise LLMError(f"预设脚本第 {self._index} 步的 tool_call 缺少 name。")
            self._call_count += 1
            call_id = f"call_{self._call_count}"
            arguments = _raw_arguments(spec.get("arguments"))
            calls.append(
                ToolCall(id=call_id, name=str(spec["name"]), arguments=arguments)
            )
            raw_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": str(spec["name"]), "arguments": arguments},
                }
            )
        return LLMResponse(
            content=None,
            tool_calls=calls,
            raw_message={"role": "assistant", "content": None, "tool_calls": raw_calls},
            usage=self._zero_usage(),
        )

    @staticmethod
    def _zero_usage() -> dict:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
