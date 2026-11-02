"""运行记录：把每一步动作、观察结果和决策依据写成 trace.jsonl 与 trace.md。"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import AgentResult

# 这些动作的参数里带完整脚本，trace.md 只显示标题和分镜数。
_SCRIPT_ACTIONS = {"estimate_duration", "check_rules", "submit_script"}

# 模型内部思维字段不写入 Trace；即使被误塞进工具参数也在这里丢掉。
_INTERNAL_KEYS = {
    "reasoning_content",
    "reasoning",
    "reasoning_details",
    "thinking",
    "chain_of_thought",
    "internal_thought",
}

# 参数名命中这些值时整项不写；值里的密钥样式再做一次脱敏。
_SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "secret",
    "client_secret",
    "password",
    "passwd",
    "access_token",
    "accesstoken",
    "refresh_token",
    "refreshtoken",
}
_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9._\-]{4,}")


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _num(value: Any) -> str:
    """数字用 f"{x:g}"，字段缺失或类型不对时返回可读占位，不抛异常。"""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        try:
            return f"{value:g}"
        except (ValueError, OverflowError):
            return str(value)
    return "未知" if value is None else str(value)


def _clip(text: Any, limit: int = 80) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _redact_text(text: str) -> str:
    return _KEY_PATTERN.sub("sk-***", text)


def _clean(value: Any) -> Any:
    """递归复制并去掉模型内部字段、密钥字段，字符串里的密钥样式也脱敏。"""
    if isinstance(value, dict):
        cleaned: dict = {}
        for key, item in value.items():
            name = str(key)
            normalized = name.strip().lower().replace("-", "_")
            if normalized in _INTERNAL_KEYS or normalized in _SECRET_KEYS:
                continue
            cleaned[name] = _clean(item)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        try:
            return _clean(value.model_dump(exclude_none=True))
        except (TypeError, ValueError):
            pass
    return _redact_text(str(value))


def _clean_usage(usage: Any) -> dict:
    """usage 可能是 SDK 的 pydantic 对象，统一成普通 dict；缺失时补零。"""
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0}
    if hasattr(usage, "model_dump"):
        try:
            usage = usage.model_dump(exclude_none=True)
        except TypeError:
            usage = usage.model_dump()
    if not isinstance(usage, dict):
        try:
            usage = dict(usage)
        except (TypeError, ValueError):
            return {"prompt_tokens": 0, "completion_tokens": 0}
    cleaned = _clean(usage)
    for key in list(cleaned):
        if key.endswith("_tokens") and isinstance(cleaned[key], float) and cleaned[key].is_integer():
            cleaned[key] = int(cleaned[key])
    return cleaned


def _usage_total(usage: dict) -> int:
    if "prompt_tokens" in usage or "completion_tokens" in usage:
        return _int(usage.get("prompt_tokens")) + _int(usage.get("completion_tokens"))
    return _int(usage.get("total_tokens"))


def summarize_observation(action: str, observation: dict) -> str:
    """把一次工具观察压成一句中文摘要；字段缺失时返回占位，绝不抛异常。"""
    obs = observation if isinstance(observation, dict) else {}

    if obs.get("ok") is False:
        error = obs.get("error")
        if isinstance(error, dict):
            code = str(error.get("code") or "UNKNOWN_ERROR")
            message = error.get("message")
        else:
            code = str(error) if error else "UNKNOWN_ERROR"
            message = None
        if isinstance(message, str) and message.strip():
            return f"错误 {code}: {message.strip()}"
        return f"错误 {code}"

    if action == "search_materials":
        materials = obs.get("materials")
        ids = [
            str(item["id"])
            for item in materials
            if isinstance(item, dict) and item.get("id") is not None
        ] if isinstance(materials, list) else []
        count = _int(obs.get("count"), len(ids)) if "count" in obs else len(ids)
        if count <= 0:
            return "命中 0 条"
        return f"命中 {count} 条: {', '.join(ids)}" if ids else f"命中 {count} 条"

    if action == "estimate_duration":
        verdict = obs.get("verdict")
        if not verdict:
            return f"总时长 {_num(obs.get('total_duration_sec'))}s"
        head = (
            f"总时长 {_num(obs.get('total_duration_sec'))}s，"
            f"目标 {_num(obs.get('target_duration_sec'))}s，判定 {verdict}"
        )
        if verdict == "too_long":
            return f"{head}，超出 {_num(obs.get('overflow_sec'))}s"
        if verdict == "too_short":
            return f"{head}，不足 {_num(obs.get('shortfall_sec'))}s"
        return head

    if action == "check_rules":
        verdict = obs.get("verdict")
        if verdict is None:
            return "判定未知"
        if verdict == "pass":
            return "判定 pass"
        if verdict == "fail":
            codes: list[str] = []
            violations = obs.get("violations")
            for item in violations if isinstance(violations, list) else []:
                code = item.get("code") if isinstance(item, dict) else None
                if code is not None and str(code) not in codes:
                    codes.append(str(code))
            return f"判定 fail: {', '.join(codes)}" if codes else "判定 fail"
        return f"判定 {verdict}"

    if action == "submit_script":
        status = obs.get("status")
        return f"提交结果 {status}" if status and status != "completed" else "提交通过"

    if action == "ask_user":
        return "已请求用户补充信息"

    if action == "report_failure":
        return "已报告无法满足要求"

    message = obs.get("message")
    if isinstance(message, str) and message.strip():
        return _clip(message, 80)
    return "完成" if obs.get("ok") else "无结果"


def _key_args(action: str, args: Any) -> str:
    """trace.md 的“关键参数”列；脚本类动作只显示标题和分镜数。"""
    if not isinstance(args, dict) or not args:
        return "—"
    if action in _SCRIPT_ACTIONS:
        title = args.get("title")
        shots = args.get("shots")
        count = len(shots) if isinstance(shots, list) else 0
        return f"标题={_clip(title, 40) if title else '—'}；分镜={count}"
    if set(args) == {"_raw"}:
        return f"原始参数={_clip(args['_raw'], 60)}"
    parts = []
    for name, value in args.items():
        if name == "decision_note":
            continue
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False, default=str)
        elif value is None:
            rendered = "—"
        else:
            rendered = str(value)
        parts.append(f"{name}={_clip(rendered, 60)}")
    return "；".join(parts) or "—"


def _cell(value: Any) -> str:
    return _clip(value, 200).replace("|", "\\|")


class TraceRecorder:
    """按时间顺序写 trace.jsonl；finish 时回填 next_action 并渲染 trace.md。"""

    def __init__(
        self,
        out_dir: Path,
        *,
        mode: str,
        model: str,
        request: dict,
        fault: dict | None,
        max_steps: int,
        max_tool_calls: int,
    ) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._jsonl_path = self.out_dir / "trace.jsonl"
        self._md_path = self.out_dir / "trace.md"

        self.run_id = uuid.uuid4().hex
        self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._records: list[dict] = []
        self._steps: list[dict] = []
        self._notes: list[dict] = []
        self._usage_by_round: dict[int, dict] = {}
        self._finished = False

        self._append({
            "type": "run_start",
            "run_id": self.run_id,
            "mode": str(mode),
            "model": str(model),
            "started_at": self.started_at,
            "request": _clean(request) if isinstance(request, dict) else {},
            "fault": _clean(fault) if isinstance(fault, dict) else None,
            "max_steps": _int(max_steps),
            "max_tool_calls": _int(max_tool_calls),
        })

    def step(
        self,
        *,
        round: int,
        seq: int,
        action: str,
        args: dict,
        observation: dict,
        decision_note: str,
        injected_fault: bool,
        usage: dict,
    ) -> None:
        self._ensure_open()
        round_no = _int(round)
        usage_dict = _clean_usage(usage)
        # 同一轮内多个工具调用共享同一份 usage，只按轮记一次。
        # 若先记到空 usage、后面才拿到真实用量，用非空的那份覆盖。
        existing = self._usage_by_round.get(round_no)
        if existing is None or (
            _usage_total(existing) == 0 and _usage_total(usage_dict) > 0
        ):
            self._usage_by_round[round_no] = usage_dict
        record = {
            "type": "step",
            "round": round_no,
            "seq": _int(seq),
            "action": str(action),
            "args": _clean(args) if isinstance(args, dict) else {"_raw": str(args)},
            "result_summary": summarize_observation(str(action), observation),
            "result": _clean(observation) if isinstance(observation, dict) else {},
            "decision_note": _redact_text(str(decision_note or "")),
            "next_action": None,
            "injected_fault": bool(injected_fault),
            "usage": usage_dict,
        }
        self._steps.append(record)
        self._append(record)

    def note(self, *, round: int, event: str, detail: str) -> None:
        self._ensure_open()
        record = {
            "type": "note",
            "round": _int(round),
            "event": str(event),
            # note 的 detail 是自由文本，同样要挡掉密钥样式。
            "detail": _redact_text(_clip(detail, 300)),
        }
        self._notes.append(record)
        self._append(record)

    def finish(self, result: AgentResult) -> None:
        if self._finished:
            return
        status = result.status
        for index, step in enumerate(self._steps):
            if index + 1 < len(self._steps):
                step["next_action"] = self._steps[index + 1]["action"]
            else:
                step["next_action"] = f"END:{status}"
        self._records.append({
            "type": "run_end",
            "status": status,
            "steps_used": _int(result.steps_used),
            "tool_calls_used": _int(result.tool_calls_used),
            "total_tokens": self._total_tokens(),
        })
        # 步骤是边跑边追加的，finish 时用回填后的记录整体重写。
        self._write_jsonl()
        self._write_markdown()
        self._finished = True

    # -- 内部 ---------------------------------------------------------------

    def _ensure_open(self) -> None:
        if self._finished:
            raise RuntimeError("Trace 已经结束，不能再追加记录")

    def _append(self, record: dict) -> None:
        self._records.append(record)
        with self._jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _write_jsonl(self) -> None:
        text = "\n".join(
            json.dumps(record, ensure_ascii=False, default=str)
            for record in self._records
        )
        self._jsonl_path.write_text(text + "\n", encoding="utf-8")

    def _total_tokens(self) -> int:
        return sum(_usage_total(usage) for usage in self._usage_by_round.values())

    def _write_markdown(self) -> None:
        lines = [
            "# Trace",
            "",
            "| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |",
            "|---:|---|---|---|---|---|",
        ]
        for step in self._steps:
            cells = [
                _cell(step["seq"]),
                _cell(step["action"]),
                _cell(_key_args(step["action"], step["args"])),
                _cell(step["result_summary"]),
                _cell(step["next_action"] or ""),
                _cell(step["decision_note"]),
            ]
            lines.append("| " + " | ".join(cells) + " |")
        if self._notes:
            lines += ["", "## 备注", ""]
            for note in self._notes:
                lines.append(
                    f"- 轮 {note['round']} · `{note['event']}`：{_cell(note['detail'])}"
                )
        self._md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
