"""ReAct 循环：模型决策，代码只做步骤上限、消息协议和收尾的护栏。"""

from __future__ import annotations

import json

from .llm import LLMClient, LLMError
from .models import AgentResult, ScriptRequest
from .prompts import NUDGE, SYSTEM_PROMPT, build_user_message
from .registry import ToolRegistry
from .trace import TraceRecorder

_LLM_ERROR_PREFIX = "模型调用失败"


def _no_action_detail(content: str | None) -> str:
    """文字回复不算行动；把内容截一段写进 Trace，便于排查模型为何停住。"""
    if not content:
        return "模型没有调用工具，也没有给出文字回复。"
    flat = " ".join(str(content).split())
    excerpt = flat if len(flat) <= 120 else flat[:119] + "…"
    return f"模型只回复了文字，没有调用工具：{excerpt}"


def _llm_failure_message(exc: LLMError) -> str:
    """统一以“模型调用失败”开头；客户端已经加过前缀时不重复。"""
    detail = str(exc).strip() or type(exc).__name__
    if detail.startswith(_LLM_ERROR_PREFIX):
        return detail
    return f"{_LLM_ERROR_PREFIX}：{detail}"


def run_agent(
    request: ScriptRequest,
    llm: LLMClient,
    registry: ToolRegistry,
    trace: TraceRecorder,
    *,
    mode: str,
    max_steps: int = 10,
    max_tool_calls: int = 20,
) -> AgentResult:
    """按 brief 的循环算法驱动模型：唯一决策者是模型，代码只负责护栏与收尾。

    steps_used 是实际发起的模型调用轮数（抛 LLMError 的那轮也已发起，计在内）；
    tool_calls_used 只统计真正交给注册表执行的调用。
    """
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(request)},
    ]
    seq = 0
    steps_used = 0
    tool_calls_used = 0
    result: AgentResult | None = None

    for round_no in range(1, max_steps + 1):
        steps_used = round_no
        try:
            resp = llm.complete(messages, registry.schemas())
        except LLMError as exc:
            result = registry.build_result(
                "failed",
                mode=mode,
                steps_used=steps_used,
                tool_calls_used=tool_calls_used,
                message=_llm_failure_message(exc),
            )
            break

        # 原样回传 assistant 消息，保留 tool_calls 与厂商附加字段。
        messages.append(resp.raw_message)

        if not resp.tool_calls:
            trace.note(
                round=round_no,
                event="no_action",
                detail=_no_action_detail(resp.content),
            )
            messages.append({"role": "user", "content": NUDGE})
            continue

        for tool_call in resp.tool_calls:
            if tool_calls_used >= max_tool_calls:
                result = registry.build_result(
                    "incomplete",
                    mode=mode,
                    steps_used=steps_used,
                    tool_calls_used=tool_calls_used,
                    message=f"达到工具调用上限（{max_tool_calls}），任务未完成。",
                )
                break

            outcome = registry.execute(tool_call.name, tool_call.arguments)
            tool_calls_used += 1
            seq += 1
            trace.step(
                round=round_no,
                seq=seq,
                action=outcome.action,
                args=outcome.args,
                observation=outcome.observation,
                decision_note=outcome.decision_note,
                injected_fault=outcome.injected_fault,
                usage=resp.usage,
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(outcome.observation, ensure_ascii=False),
                }
            )

            # 终止动作之后的 tool_call 不再执行。
            if outcome.terminal:
                result = registry.build_result(
                    outcome.terminal,
                    mode=mode,
                    steps_used=steps_used,
                    tool_calls_used=tool_calls_used,
                )
                break

        if result is not None:
            break

    if result is None:
        result = registry.build_result(
            "incomplete",
            mode=mode,
            steps_used=steps_used,
            tool_calls_used=tool_calls_used,
            message=f"达到步数上限（{max_steps}），任务未完成。",
        )

    trace.finish(result)
    return result
