"""运行记录：把每一步动作、观察结果和决策依据写成 trace.jsonl 与 trace.md。"""

from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

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
    "auth",
    "secret",
    "client_secret",
    "password",
    "passwd",
    "token",
    "access_token",
    "accesstoken",
    "refresh_token",
    "refreshtoken",
    "id_token",
    "auth_token",
    "bearer_token",
    "session_token",
}

# 这些是用量统计，不是凭据；按名字脱敏时必须放行，否则 token 计数会丢。
_USAGE_TOKEN_KEYS = {
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "max_tokens",
}

_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9._\-]{4,}")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_KEY_SEPARATORS = re.compile(r"[\s\-]+")
_KEY_UNDERSCORES = re.compile(r"_+")


def _normalize_key(name: object) -> str:
    """clientSecret / x-api-key / OPENAI_API_KEY 统一成 snake_case 小写。"""
    text = str(name).strip()
    text = _CAMEL_BOUNDARY.sub("_", text)
    text = _KEY_SEPARATORS.sub("_", text)
    return _KEY_UNDERSCORES.sub("_", text).strip("_").lower()


def _is_secret_key(name: object) -> bool:
    """判断参数名是否属于凭据：精确名、前缀形式（x-api-key）与驼峰形式都算。"""
    normalized = _normalize_key(name)
    if not normalized:
        return False
    if normalized in _SECRET_KEYS:
        return True
    if "api_key" in normalized or "apikey" in normalized:
        return True
    if "secret" in normalized:
        return True
    if normalized.startswith("authorization") or normalized.endswith(
        "_authorization"
    ):
        return True
    # 用量统计（复数 _tokens）不是凭据，不能删。
    if normalized in _USAGE_TOKEN_KEYS or normalized.endswith("_tokens"):
        return False
    # 单数 token 结尾通常是凭据：access_token / auth_token / session_token。
    if normalized == "token" or normalized.endswith("_token"):
        return True
    return False


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


def _redact_text(text: str, secrets: Iterable[str] = ()) -> str:
    """先按已知密钥字面量替换，再处理 sk- 样式；两处都要做。"""
    redacted = text
    for secret in _secret_tuple(secrets):
        if secret:
            redacted = redacted.replace(secret, "***")
    return _KEY_PATTERN.sub("sk-***", redacted)


def _clip_redacted(text: Any, limit: int, secrets: Iterable[str] = ()) -> str:
    """先脱敏再截断：反过来会把跨截断点的密钥切出残片，残片不再匹配任何规则。"""
    return _clip(_redact_text(str(text), _secret_tuple(secrets)), limit)


def _clean(value: Any, secrets: Iterable[str] = ()) -> Any:
    """递归复制并去掉模型内部字段、密钥字段，字符串里的密钥也脱敏。"""
    if isinstance(value, dict):
        cleaned: dict = {}
        for key, item in value.items():
            name = str(key)
            normalized = _normalize_key(name)
            if normalized in _INTERNAL_KEYS or _is_secret_key(name):
                continue
            cleaned[name] = _clean(item, secrets)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_clean(item, secrets) for item in value]
    if isinstance(value, str):
        return _redact_text(value, secrets)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        try:
            return _clean(value.model_dump(exclude_none=True), secrets)
        except (TypeError, ValueError):
            pass
    return _redact_text(str(value), secrets)


def _clean_usage(usage: Any, secrets: Iterable[str] = ()) -> dict:
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
    cleaned = _clean(usage, secrets)
    for key in list(cleaned):
        if key.endswith("_tokens") and isinstance(cleaned[key], float) and cleaned[key].is_integer():
            cleaned[key] = int(cleaned[key])
    return cleaned


def _usage_total(usage: dict) -> int:
    if "prompt_tokens" in usage or "completion_tokens" in usage:
        return _int(usage.get("prompt_tokens")) + _int(usage.get("completion_tokens"))
    return _int(usage.get("total_tokens"))


def _secret_tuple(secrets: Iterable[str]) -> tuple[str, ...]:
    """单个 str 按一个密钥处理，否则会被逐字符拆开；长的先替换避免残片。"""
    if isinstance(secrets, str):
        secrets = (secrets,)
    return tuple(sorted({str(item) for item in secrets if item}, key=len, reverse=True))


def summarize_observation(
    action: str, observation: dict, secrets: Iterable[str] = ()
) -> str:
    """把一次工具观察压成一句中文摘要；字段缺失时返回占位，绝不抛异常。"""
    secrets = _secret_tuple(secrets)
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
            return f"错误 {code}: {_clip_redacted(message.strip(), 200, secrets)}"
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
        # 先脱敏再截断，避免密钥跨 80 字边界被切出残片。
        return _clip_redacted(message, 80, secrets)
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
        secrets: Iterable[str] = (),
        listener: Callable[[dict], None] | None = None,
    ) -> None:
        self._listener = listener
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._jsonl_path = self.out_dir / "trace.jsonl"
        self._md_path = self.out_dir / "trace.md"
        # 已知密钥字面量：不是 sk- 形状的凭据也能从自由文本里挡掉。
        # 传单个 str 时按一个密钥处理，否则会被拆成一个个字符。
        if isinstance(secrets, str):
            secrets = (secrets,)
        # 长的先替换，避免短密钥是长密钥子串时留下残片。
        self._secrets = tuple(
            sorted({str(item) for item in secrets if item}, key=len, reverse=True)
        )

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
            "request": _clean(request, self._secrets) if isinstance(request, dict) else {},
            "fault": _clean(fault, self._secrets) if isinstance(fault, dict) else None,
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
        usage_dict = _clean_usage(usage, self._secrets)
        # 同一轮内多个工具调用共享同一份 usage，只按轮记一次。
        # 若先记到空 usage、后面才拿到真实用量，用非空的那份覆盖。
        existing = self._usage_by_round.get(round_no)
        if existing is None or (
            _usage_total(existing) == 0 and _usage_total(usage_dict) > 0
        ):
            self._usage_by_round[round_no] = usage_dict
        # 摘要会同时进 jsonl 和 md，必须和 result 一样脱敏；它来自原始 observation。
        # secrets 必须传进去：摘要内部先截断再返回，出来后再脱敏已经来不及。
        summary = summarize_observation(str(action), observation, self._secrets)
        record = {
            "type": "step",
            "round": round_no,
            "seq": _int(seq),
            "action": str(action),
            "args": (
                _clean(args, self._secrets)
                if isinstance(args, dict)
                else {"_raw": _redact_text(str(args), self._secrets)}
            ),
            "result_summary": summary,
            "result": _clean(observation, self._secrets) if isinstance(observation, dict) else {},
            "decision_note": _redact_text(str(decision_note or ""), self._secrets),
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
            # note 的 detail 是自由文本；先脱敏再截断，避免密钥跨截断点被切出残片。
            "detail": _clip_redacted(detail, 300, self._secrets),
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
        end_record = {
            "type": "run_end",
            "status": status,
            "steps_used": _int(result.steps_used),
            "tool_calls_used": _int(result.tool_calls_used),
            "total_tokens": self._total_tokens(),
        }
        self._records.append(end_record)
        # 步骤是边跑边追加的，finish 时用回填后的记录整体重写。
        self._write_jsonl()
        self._write_markdown()
        self._finished = True
        self._notify(end_record)

    # -- 内部 ---------------------------------------------------------------

    def _ensure_open(self) -> None:
        if self._finished:
            raise RuntimeError("Trace 已经结束，不能再追加记录")

    def _append(self, record: dict) -> None:
        self._records.append(record)
        with self._jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._notify(record)

    def _notify(self, record: dict) -> None:
        """把记录副本交给监听器；监听器出任何问题都不能影响运行和产物。"""
        if self._listener is None:
            return
        try:
            self._listener(copy.deepcopy(record))
        except Exception:
            pass

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
