"""跑一次 Agent，并把结果、脚本和 Trace 写到 out_dir。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .agent import run_agent
from .llm import LLMClient
from .models import AgentResult, normalize_request
from .registry import FaultPlan, ToolRegistry
from .render import render_script_markdown
from .trace import TraceRecorder


def _fault_record(fault: FaultPlan | None) -> dict | None:
    """TraceRecorder 的 fault 参数是 dict|None，FaultPlan 必须先转成普通字典。"""
    if fault is None:
        return None
    return {"tool": fault.tool, "times": fault.times}


def _secrets_from_env() -> tuple[str, ...]:
    """把真实密钥交给 TraceRecorder，非 sk- 形状的密钥也能从自由文本里脱敏。"""
    key = os.environ.get("LLM_API_KEY", "").strip()
    return (key,) if key else ()


def run_once(
    raw_request: dict,
    llm: LLMClient,
    *,
    mode: str,
    model_name: str,
    data_dir: Path,
    fault: FaultPlan | None,
    max_steps: int,
    max_tool_calls: int,
    out_dir: Path,
) -> AgentResult:
    """跑一次 Agent 并在 out_dir 写 result.json、script.md、trace.jsonl、trace.md。"""
    request = normalize_request(raw_request)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # TraceRecorder 以追加方式写 trace.jsonl；复用同一个 out_dir 时先清掉上一轮记录。
    (out_dir / "trace.jsonl").unlink(missing_ok=True)

    trace = TraceRecorder(
        out_dir,
        mode=mode,
        model=model_name,
        request=request.model_dump(),
        fault=_fault_record(fault),
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
        secrets=_secrets_from_env(),
    )
    registry = ToolRegistry(request, Path(data_dir), fault)
    result = run_agent(
        request,
        llm,
        registry,
        trace,
        mode=mode,
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
    )

    result_json = json.dumps(
        result.model_dump(mode="json"), ensure_ascii=False, indent=2
    )
    (out_dir / "result.json").write_text(result_json + "\n", encoding="utf-8")
    (out_dir / "script.md").write_text(
        render_script_markdown(result), encoding="utf-8"
    )
    return result
