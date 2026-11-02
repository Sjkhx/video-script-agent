"""工具注册表：schema、参数校验、故障注入、运行状态、提交把关与结果组装。"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .catalog import Catalog, DataError, load_catalog
from .models import (
    AgentResult,
    Checks,
    FinalShot,
    ScriptDraft,
    ScriptRequest,
    ShotDraft,
    Status,
    draft_hash,
    missing_required,
    optional_assumptions,
)
from .tools import check_rules, estimate_duration, search_materials

_BUSINESS_TOOLS = {"search_materials", "estimate_duration", "check_rules"}
_DRAFT_TOOLS = {"estimate_duration", "check_rules"}

_MissingField = Literal[
    "topic",
    "audience",
    "platform",
    "target_duration_sec",
    "style",
    "materials",
    "other",
]


# ---------------------------------------------------------------------------
# 参数模型：decision_note 必填且非空；长度不校验，避免模型多写几个字就浪费一步。
# 模型多传的字段由 pydantic 丢弃（extra="ignore"）。
# ---------------------------------------------------------------------------


class _ArgsBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    decision_note: str = Field(
        min_length=1,
        description="这一步的决策依据：是哪个观察结果让你选择这个动作，不超过 40 字。",
    )

    @field_validator("decision_note")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("decision_note 不能为空")
        return value


class _SearchArgs(_ArgsBase):
    query: str = Field(min_length=1)
    # search_materials 用 hits[:top_k] 截断，越界值必须在校验层拦下。
    top_k: int = Field(default=5, ge=1, le=10)


class _DraftArgs(_ArgsBase):
    title: str = Field(min_length=1)
    shots: list[ShotDraft] = Field(min_length=1)


class _SubmitArgs(_DraftArgs):
    risks: list[str] = []


class _AskUserArgs(_ArgsBase):
    missing_fields: list[_MissingField] = Field(min_length=1)
    questions: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)


class _ReportFailureArgs(_ArgsBase):
    reason: str = Field(min_length=1)
    unmet_requirements: list[str] = []
    failed_tools: list[str] = []


_ARG_MODELS: dict[str, type[_ArgsBase]] = {
    "search_materials": _SearchArgs,
    "estimate_duration": _DraftArgs,
    "check_rules": _DraftArgs,
    "submit_script": _SubmitArgs,
    "ask_user": _AskUserArgs,
    "report_failure": _ReportFailureArgs,
}


# ---------------------------------------------------------------------------
# JSON Schema：全部手写普通 schema，不产生 $ref；decision_note 对所有工具必填。
# 不提供时长字段和目标时长字段，时长只能来自工具结果。
# ---------------------------------------------------------------------------

_DECISION_NOTE_SCHEMA = {
    "type": "string",
    "description": "这一步的决策依据：是哪个观察结果让你选择这个动作，不超过 40 字。",
}

_SHOT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "description": "分镜序号"},
        "visual": {"type": "string", "description": "画面内容"},
        "narration": {"type": "string", "description": "旁白或字幕"},
        "claims": {
            "type": "array",
            "description": "这一镜引用的产品事实；quote 必须是素材 facts 的逐字原文。",
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string", "description": "素材 ID"},
                    "quote": {"type": "string", "description": "素材原文"},
                },
                "required": ["source_id", "quote"],
            },
        },
    },
    "required": ["id", "visual", "narration"],
}

_DRAFT_PROPERTIES = {
    "title": {"type": "string", "description": "脚本标题"},
    "shots": {
        "type": "array",
        "minItems": 1,
        "items": _SHOT_SCHEMA,
        "description": "完整脚本的分镜列表",
    },
}


def _parameters(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {**properties, "decision_note": _DECISION_NOTE_SCHEMA},
        "required": [*required, "decision_note"],
    }


_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_materials",
            "description": "检索产品素材。返回本次命中的素材 ID 与事实；脚本里的产品事实只能来自这里。",
            "parameters": _parameters(
                {
                    "query": {
                        "type": "string",
                        "description": "检索词，可用空格或逗号分隔",
                    },
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 5,
                        "description": "最多返回几条素材",
                    },
                },
                ["query"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_duration",
            "description": "估算完整脚本的时长。返回每个分镜的时长、总时长和时长判定；时长以它的返回为准。",
            "parameters": _parameters(_DRAFT_PROPERTIES, ["title", "shots"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_rules",
            "description": "检查品牌规则与素材来源。返回 verdict 和 violations；规则以它的返回为准。",
            "parameters": _parameters(_DRAFT_PROPERTIES, ["title", "shots"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_script",
            "description": "提交已通过时长和规则检查的完整脚本。只有同一份脚本的 duration 与 rules 都通过时才会被接受。",
            "parameters": _parameters(
                {
                    **_DRAFT_PROPERTIES,
                    "risks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                        "description": "仍需说明的风险",
                    },
                },
                ["title", "shots"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "缺少关键信息或素材时请求用户补充；调用后任务结束。",
            "parameters": _parameters(
                {
                    "missing_fields": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "string",
                            "enum": [
                                "topic",
                                "audience",
                                "platform",
                                "target_duration_sec",
                                "style",
                                "materials",
                                "other",
                            ],
                        },
                        "description": "缺失的信息类别",
                    },
                    "questions": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                        "description": "要问用户的问题",
                    },
                    "reason": {"type": "string", "description": "为什么需要补充"},
                },
                ["missing_fields", "questions", "reason"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_failure",
            "description": "确认无法满足要求时说明原因；调用后任务结束。",
            "parameters": _parameters(
                {
                    "reason": {"type": "string", "description": "失败原因"},
                    "unmet_requirements": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                        "description": "未满足的要求",
                    },
                    "failed_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                        "description": "失败的工具名",
                    },
                },
                ["reason"],
            ),
        },
    },
]


# ---------------------------------------------------------------------------
# 返回值
# ---------------------------------------------------------------------------


@dataclass
class FaultPlan:
    tool: str
    times: int  # -1 表示一直失败


@dataclass
class ToolOutcome:
    action: str
    args: dict  # 不含 decision_note；参数不是合法 JSON 时为 {"_raw": 原始字符串}
    observation: dict  # 回给模型的内容
    decision_note: str
    injected_fault: bool = False
    terminal: Literal["completed", "needs_input", "failed"] | None = None


def _error(code: str, message: str, **extra: object) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, **extra}}


def _raw_args(raw_arguments: str) -> dict:
    return {"_raw": raw_arguments}


def _parse_json_object(raw_arguments: str) -> dict | None:
    try:
        payload = json.loads(raw_arguments)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _note_of(payload: dict) -> str:
    value = payload.get("decision_note")
    return value if isinstance(value, str) else ""


def _without_note(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key != "decision_note"}


def _validation_message(exc: ValidationError) -> str:
    details = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "参数"
        details.append(f"{location}: {error['msg']}")
    return "参数校验失败：" + "；".join(details)


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------


class ToolRegistry:
    """有状态的工具网关：校验、故障注入、记录检查结果、提交把关、组装结果。"""

    def __init__(
        self,
        request: ScriptRequest,
        data_dir: Path,
        fault: FaultPlan | None = None,
    ) -> None:
        self._request = request
        self._data_dir = Path(data_dir)
        # 复制一份，注入次数只在本注册表内消耗，不修改调用方传入的对象。
        self._fault = (
            FaultPlan(tool=fault.tool, times=fault.times) if fault is not None else None
        )

        self._catalog: Catalog | None = None
        self._consecutive_failures: dict[str, int] = {}

        self._retrieved_ids: set[str] = set()
        self._checks_by_hash: dict[str, dict[str, str]] = {}
        self._estimates_by_hash: dict[str, dict] = {}
        self._last_draft: ScriptDraft | None = None
        self._last_estimate: dict | None = None

        self._submitted_draft: ScriptDraft | None = None
        self._submitted_hash: str | None = None
        self._model_risks: list[str] = []

        self._missing_fields: list[str] = []
        self._questions: list[str] = []
        self._ask_reason: str = ""

        self._failure_reason: str = ""
        self._unmet_requirements: list[str] = []

    def schemas(self) -> list[dict]:
        """六个工具的 OpenAI function schema，全部普通 JSON Schema，不含 $ref。"""
        return deepcopy(_TOOL_SCHEMAS)

    # -- 执行 ---------------------------------------------------------------

    def execute(self, name: str, raw_arguments: str) -> ToolOutcome:
        """按 brief 的 8 个步骤处理一次工具调用；任何情况都不抛异常给调用方。"""
        # 步骤 1：工具名未知。
        if name not in _ARG_MODELS:
            return ToolOutcome(
                action=name,
                args=_raw_args(raw_arguments),
                observation=_error("UNKNOWN_TOOL", f"未知工具：{name}"),
                decision_note="",
            )

        # 步骤 2：解析 JSON 并校验参数（含 decision_note）。不通过不计入连续失败。
        payload = _parse_json_object(raw_arguments)
        if payload is None:
            return ToolOutcome(
                action=name,
                args=_raw_args(raw_arguments),
                observation=_error("INVALID_ARGS", "参数必须是合法的 JSON 对象。"),
                decision_note="",
            )
        note = _note_of(payload)
        try:
            parsed = _ARG_MODELS[name].model_validate(payload)
        except ValidationError as exc:
            return ToolOutcome(
                action=name,
                args=_without_note(payload),
                observation=_error("INVALID_ARGS", _validation_message(exc)),
                decision_note=note,
            )
        args_view = parsed.model_dump(exclude={"decision_note"})

        # 步骤 3：estimate_duration / check_rules 先把通过校验的草稿记为 last_draft。
        # 这一步在故障注入之前，因此工具失败时也能保留草稿。
        draft: ScriptDraft | None = None
        hashed: str | None = None
        if name in _DRAFT_TOOLS:
            draft = ScriptDraft(title=parsed.title, shots=parsed.shots)
            hashed = draft_hash(draft)
            self._last_draft = draft

        # 步骤 4：三个业务工具先判断故障，再懒加载 Catalog；失败都带 retries_left。
        if name in _BUSINESS_TOOLS:
            if self._take_fault(name):
                return self._business_failure(
                    name,
                    "TOOL_UNAVAILABLE",
                    f"工具 {name} 当前不可用，请稍后重试。",
                    args_view,
                    note,
                    hashed,
                    injected=True,
                )
            try:
                catalog = self._load_catalog()
            except DataError as exc:
                return self._business_failure(
                    name,
                    "DATA_UNAVAILABLE",
                    f"数据不可用：{exc}",
                    args_view,
                    note,
                    hashed,
                )

            # 步骤 6的两种可预期问题：不当作工具失败，不计入连续失败。
            if name == "search_materials":
                try:
                    result = search_materials(catalog, parsed.query, parsed.top_k)
                except ValueError as exc:
                    return ToolOutcome(
                        action=name,
                        args=args_view,
                        observation=_error(
                            "INVALID_ARGS", f"检索参数不合法：{exc}"
                        ),
                        decision_note=note,
                    )
                except Exception as exc:  # 工具内部异常算工具失败
                    return self._business_failure(
                        name,
                        "TOOL_EXCEPTION",
                        f"工具 {name} 执行出错：{exc}",
                        args_view,
                        note,
                        hashed,
                    )
            elif name == "estimate_duration":
                target = self._request.target_duration_sec
                if target is None:
                    return ToolOutcome(
                        action=name,
                        args=args_view,
                        observation=_error(
                            "MISSING_TARGET", "请求中没有有效的目标时长，无法估算时长。"
                        ),
                        decision_note=note,
                    )
                assert draft is not None
                try:
                    result = estimate_duration(catalog.duration, draft, target)
                except Exception as exc:
                    return self._business_failure(
                        name,
                        "TOOL_EXCEPTION",
                        f"工具 {name} 执行出错：{exc}",
                        args_view,
                        note,
                        hashed,
                    )
            else:  # check_rules
                assert draft is not None
                try:
                    result = check_rules(catalog, draft, self._retrieved_ids)
                except Exception as exc:
                    return self._business_failure(
                        name,
                        "TOOL_EXCEPTION",
                        f"工具 {name} 执行出错：{exc}",
                        args_view,
                        note,
                        hashed,
                    )

            # 工具成功：同一工具的连续失败次数归零。
            self._consecutive_failures.pop(name, None)

            # 步骤 5：更新运行状态。
            if name == "search_materials":
                self._retrieved_ids.update(
                    material["id"] for material in result["materials"]
                )
            elif name == "estimate_duration":
                assert hashed is not None
                self._last_estimate = result
                self._estimates_by_hash[hashed] = result
                self._checks_by_hash.setdefault(hashed, {})["duration"] = result[
                    "verdict"
                ]
            else:
                assert hashed is not None
                self._checks_by_hash.setdefault(hashed, {})["rules"] = result["verdict"]

            return ToolOutcome(
                action=name, args=args_view, observation=result, decision_note=note
            )

        # 步骤 7：提交把关。请求完整、且同一份草稿的 duration 与 rules 都是 pass
        # 才通关；否则返回 GATE_REJECTED，流程继续。
        if name == "submit_script":
            submitted = ScriptDraft(title=parsed.title, shots=parsed.shots)
            submitted_hash = draft_hash(submitted)
            checks = self._checks_by_hash.get(submitted_hash, {})
            reasons: list[str] = []
            missing = missing_required(self._request)
            if missing:
                reasons.append(
                    f"请求缺少必填信息：{'、'.join(missing)}，请先向用户确认。"
                )
            if checks.get("duration") != "pass":
                reasons.append(
                    "这份脚本的 duration 检查不是 pass"
                    f"（当前 {checks.get('duration', 'not_run')}），请重新估算时长。"
                )
            if checks.get("rules") != "pass":
                reasons.append(
                    "这份脚本的 rules 检查不是 pass"
                    f"（当前 {checks.get('rules', 'not_run')}），请重新检查品牌规则。"
                )
            if reasons:
                return ToolOutcome(
                    action=name,
                    args=args_view,
                    observation=_error(
                        "GATE_REJECTED", "提交未通过把关。", reasons=reasons
                    ),
                    decision_note=note,
                )
            self._submitted_draft = submitted
            self._submitted_hash = submitted_hash
            self._model_risks = list(parsed.risks)
            return ToolOutcome(
                action=name,
                args=args_view,
                observation={
                    "ok": True,
                    "status": "completed",
                    "message": "提交已通过把关。",
                },
                decision_note=note,
                terminal="completed",
            )

        # 步骤 8：另外两个终止动作。
        if name == "ask_user":
            self._missing_fields = list(parsed.missing_fields)
            self._questions = list(parsed.questions)
            self._ask_reason = parsed.reason
            return ToolOutcome(
                action=name,
                args=args_view,
                observation={
                    "ok": True,
                    "status": "needs_input",
                    "message": self._ask_message(),
                },
                decision_note=note,
                terminal="needs_input",
            )

        self._failure_reason = parsed.reason
        self._unmet_requirements = list(parsed.unmet_requirements)
        return ToolOutcome(
            action=name,
            args=args_view,
            observation={
                "ok": True,
                "status": "failed",
                "message": self._failure_message("任务失败。"),
            },
            decision_note=note,
            terminal="failed",
        )

    # -- 内部状态 -----------------------------------------------------------

    def _load_catalog(self) -> Catalog:
        if self._catalog is None:
            self._catalog = load_catalog(self._data_dir)
        return self._catalog

    def _take_fault(self, name: str) -> bool:
        """本次调用是否注入故障；正数次数用一次减一，-1 表示一直失败。"""
        fault = self._fault
        if fault is None or fault.tool != name or fault.times == 0:
            return False
        if fault.times > 0:
            fault.times -= 1
        return True

    def _business_failure(
        self,
        name: str,
        code: str,
        message: str,
        args_view: dict,
        note: str,
        hashed: str | None,
        *,
        injected: bool = False,
    ) -> ToolOutcome:
        """工具失败：计入连续失败，返回 retries_left；检查工具同时记为 error。"""
        count = self._consecutive_failures.get(name, 0) + 1
        self._consecutive_failures[name] = count
        retries_left = max(0, 2 - count)
        if hashed is not None:
            key = "duration" if name == "estimate_duration" else "rules"
            self._checks_by_hash.setdefault(hashed, {})[key] = "error"
        return ToolOutcome(
            action=name,
            args=args_view,
            observation=_error(code, message, retries_left=retries_left),
            decision_note=note,
            injected_fault=injected,
        )

    def _checks_from_draft(self, draft: ScriptDraft | None) -> Checks:
        if draft is None:
            return Checks()
        values = self._checks_by_hash.get(draft_hash(draft), {})
        return Checks(
            duration=values.get("duration", "not_run"),
            rules=values.get("rules", "not_run"),
        )

    def _ask_message(self) -> str:
        parts: list[str] = []
        if self._ask_reason:
            parts.append(f"原因：{self._ask_reason}")
        if self._missing_fields:
            parts.append("缺少信息：" + "、".join(self._missing_fields))
        if self._questions:
            parts.append("需要确认：" + "；".join(self._questions))
        return "；".join(parts) or "需要用户补充信息。"

    def _failure_message(self, fallback: str) -> str:
        parts: list[str] = []
        if self._failure_reason:
            parts.append(self._failure_reason)
        if self._unmet_requirements:
            parts.append("未满足的要求：" + "；".join(self._unmet_requirements))
        return "；".join(parts) or fallback

    # -- 结果组装 -----------------------------------------------------------

    def build_result(
        self,
        status: Status,
        *,
        mode: str,
        steps_used: int,
        tool_calls_used: int,
        message: str | None = None,
    ) -> AgentResult:
        """按 brief 的 build_result 表组装最终结果。"""
        if status == "completed":
            return self._completed_result(mode, steps_used, tool_calls_used, message)

        checks = self._checks_from_draft(self._last_draft)
        if status == "needs_input":
            return AgentResult(
                status=status,
                message=self._ask_message() if message is None else message,
                mode=mode,
                target_duration_sec=self._request.target_duration_sec,
                checks=checks,
                missing_info=list(self._missing_fields),
                steps_used=steps_used,
                tool_calls_used=tool_calls_used,
            )

        fallback = "任务未完成。" if status == "incomplete" else "任务失败。"
        return AgentResult(
            status=status,
            message=self._failure_message(fallback) if message is None else message,
            mode=mode,
            target_duration_sec=self._request.target_duration_sec,
            checks=checks,
            unverified_draft=self._last_draft,
            last_estimate=self._last_estimate,
            steps_used=steps_used,
            tool_calls_used=tool_calls_used,
        )

    def _completed_result(
        self,
        mode: str,
        steps_used: int,
        tool_calls_used: int,
        message: str | None,
    ) -> AgentResult:
        if self._submitted_draft is None or self._submitted_hash is None:
            raise RuntimeError("没有通过把关的草稿，无法组装 completed 结果")
        estimate = self._estimates_by_hash.get(self._submitted_hash)
        if estimate is None:
            raise RuntimeError("缺少通关草稿的时长估算，无法组装 completed 结果")

        draft = self._submitted_draft
        # 时长只取自工具结果，模型传来的 duration_sec 在参数校验时就被丢弃了。
        shots = [
            FinalShot(
                **shot.model_dump(),
                duration_sec=estimated["duration_sec"],
                source_ids=sorted({claim.source_id for claim in shot.claims}),
            )
            for shot, estimated in zip(
                draft.shots, estimate["shots"], strict=True
            )
        ]
        total = estimate["total_duration_sec"]
        return AgentResult(
            status="completed",
            message=(
                f"脚本已通过时长与规则检查，共 {len(shots)} 个分镜，"
                f"预计总时长 {total} 秒。"
                if message is None
                else message
            ),
            mode=mode,
            title=draft.title,
            shots=shots,
            total_duration_sec=total,
            target_duration_sec=self._request.target_duration_sec,
            source_ids=sorted(
                {source_id for shot in shots for source_id in shot.source_ids}
            ),
            checks=self._checks_from_draft(draft),
            risks=list(self._model_risks) + optional_assumptions(self._request),
            steps_used=steps_used,
            tool_calls_used=tool_calls_used,
        )
