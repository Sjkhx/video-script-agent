from __future__ import annotations

import hashlib
import math
from typing import Literal

from pydantic import BaseModel, Field

MAX_TARGET_SEC = 600


class ScriptRequest(BaseModel):
    topic: str | None = None
    audience: str | None = None
    platform: str | None = None
    target_duration_sec: float | None = None
    style: str | None = None
    invalid_fields: dict[str, str] = {}


def _parse_target_duration(value: object) -> tuple[float | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, "目标时长不能是布尔值"
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("秒"):
            text = text[:-1].strip()
        elif text.lower().endswith("s"):
            text = text[:-1].strip()
        try:
            number = float(text)
        except ValueError:
            return None, "目标时长无法解析为数字"
    else:
        return None, "目标时长必须是数字或文本"
    if not math.isfinite(number):
        return None, "目标时长必须是有限数字"
    if number <= 0:
        return None, "目标时长必须大于 0"
    if number > MAX_TARGET_SEC:
        return None, f"目标时长不能超过 {MAX_TARGET_SEC} 秒"
    return number, None


def normalize_request(raw: dict) -> ScriptRequest:
    """规范化输入：文本去空白，空串视为缺失，目标时长解析为秒数。"""
    invalid_fields: dict[str, str] = {}
    target_duration_sec, reason = _parse_target_duration(raw.get("target_duration_sec"))
    if reason is not None:
        invalid_fields["target_duration_sec"] = reason

    texts: dict[str, str | None] = {}
    for field in ("topic", "audience", "platform", "style"):
        value = raw.get(field)
        if isinstance(value, str):
            value = value.strip() or None
        texts[field] = value

    return ScriptRequest(
        **texts,
        target_duration_sec=target_duration_sec,
        invalid_fields=invalid_fields,
    )


def missing_required(req: ScriptRequest) -> list[str]:
    """返回缺失的必填字段，顺序固定：topic、target_duration_sec。"""
    missing: list[str] = []
    if req.topic is None:
        missing.append("topic")
    if req.target_duration_sec is None:
        missing.append("target_duration_sec")
    return missing


def optional_assumptions(req: ScriptRequest) -> list[str]:
    """缺 audience/platform/style 时每项给出一个假设说明。"""
    assumptions: list[str] = []
    if req.audience is None:
        assumptions.append("未指定受众，默认面向普通短视频观众。")
    if req.platform is None:
        assumptions.append("未指定平台，默认按通用短视频平台处理。")
    if req.style is None:
        assumptions.append("未指定风格，默认采用轻松直白的风格。")
    return assumptions


class Claim(BaseModel):
    source_id: str
    quote: str


class ShotDraft(BaseModel):
    id: int
    visual: str = Field(min_length=1)
    narration: str = Field(min_length=1)
    claims: list[Claim] = []


class ScriptDraft(BaseModel):
    title: str = Field(min_length=1)
    shots: list[ShotDraft] = Field(min_length=1)


def draft_hash(draft: ScriptDraft) -> str:
    """sha256(draft.model_dump_json())，用于判断草稿内容是否变化。"""
    return hashlib.sha256(draft.model_dump_json().encode("utf-8")).hexdigest()


class FinalShot(ShotDraft):
    duration_sec: float
    source_ids: list[str]


class Checks(BaseModel):
    duration: Literal["pass", "too_long", "too_short", "error", "not_run"] = "not_run"
    rules: Literal["pass", "fail", "error", "not_run"] = "not_run"


Status = Literal["completed", "needs_input", "failed", "incomplete"]


class AgentResult(BaseModel):
    status: Status
    message: str
    mode: Literal["real", "mock"]
    title: str | None = None
    shots: list[FinalShot] | None = None
    total_duration_sec: float | None = None
    target_duration_sec: float | None = None
    source_ids: list[str] = []
    checks: Checks = Checks()
    risks: list[str] = []
    missing_info: list[str] = []
    unverified_draft: ScriptDraft | None = None
    last_estimate: dict | None = None
    steps_used: int = 0
    tool_calls_used: int = 0
