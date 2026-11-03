"""Web 接口的业务逻辑：只编排已有能力，不参与 Agent 决策。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field, field_validator

from ..catalog import Catalog, DataError, load_catalog
from ..llm import LLMClient, LLMError, OpenAICompatibleLLM, ScriptedLLM
from ..models import (
    MAX_TARGET_SEC,
    AgentResult,
    Checks,
    FinalShot,
    ScriptDraft,
)
from ..registry import FaultPlan
from ..render import render_script_markdown
from ..tools import check_rules, estimate_duration
from .runs import RunBusy, RunManager, RunSpec, read_trace

_FAULT_TOOLS = ("search_materials", "estimate_duration", "check_rules")
_MAX_TOOL_CALLS = 20
_MOCK_MODEL_NAME = "scripted"

# 客户端只能传这些 ID，路径由服务端决定。
_DATA_SETS = {
    "default": ("默认素材", "data"),
    "no_subtitle": ("缺字幕素材（无 P01）", "examples/data_variants/no_subtitle"),
    "entertainment": (
        "娱乐向素材（表情包/音效/反转）",
        "examples/data_variants/entertainment",
    ),
}
_MOCK_SCRIPTS = {
    "01_normal": "正常路径",
    "06_over_duration_fixed": "先超时长再修正",
}
_FIELD_LABELS = {"visual": "画面", "narration": "旁白"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: object) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra


class _RequestBody(BaseModel):
    topic: str | None = Field(default=None, max_length=200)
    audience: str | None = Field(default=None, max_length=200)
    platform: str | None = Field(default=None, max_length=200)
    style: str | None = Field(default=None, max_length=200)
    # 无效值原样交给 normalize_request，由模型决定怎么追问。
    target_duration_sec: Any = None


class _FaultBody(BaseModel):
    tool: Literal["search_materials", "estimate_duration", "check_rules"]
    times: int

    @field_validator("times")
    @classmethod
    def _check_times(cls, value: int) -> int:
        if value != -1 and value < 1:
            raise ValueError("times 只能是 -1 或大于等于 1 的整数")
        return value


class _RunBody(BaseModel):
    request: _RequestBody = Field(default_factory=_RequestBody)
    mode: Literal["real", "mock"]
    mock_script: str | None = None
    data_set: str = "default"
    fault: _FaultBody | None = None
    max_steps: int = Field(default=10, ge=1, le=20)


class _SourceBody(BaseModel):
    kind: Literal["run", "example"]
    id: str


class _ClaimBody(BaseModel):
    source_id: str = Field(max_length=64)
    quote: str = Field(max_length=2000)


class _ShotBody(BaseModel):
    id: int
    visual: str = Field(max_length=2000)
    narration: str = Field(max_length=2000)
    claims: list[_ClaimBody] = Field(default_factory=list, max_length=50)


class _DraftBody(BaseModel):
    title: str = Field(max_length=200)
    shots: list[_ShotBody] = Field(min_length=1, max_length=50)


class _VerifyBody(BaseModel):
    # 只收来源和草稿；目标时长、素材库、已检索素材都由服务端决定。
    source: _SourceBody
    draft: _DraftBody


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _reject_blank_fields(draft: _DraftBody) -> None:
    if not draft.title.strip():
        raise ApiError(
            422, "BLANK_FIELD", "标题不能为空。", shot_id=None, field="title"
        )
    for position, shot in enumerate(draft.shots, start=1):
        for field_name, label in _FIELD_LABELS.items():
            if not getattr(shot, field_name).strip():
                raise ApiError(
                    422,
                    "BLANK_FIELD",
                    f"第 {position} 个分镜的{label}不能为空。",
                    shot_id=shot.id,
                    field=field_name,
                )


def _retrieved_ids(records: list[dict]) -> set[str]:
    """已检索素材只认 Trace 里真实成功的检索结果。"""
    ids: set[str] = set()
    for record in records:
        if record.get("type") != "step" or record.get("action") != "search_materials":
            continue
        result = record.get("result")
        if not isinstance(result, dict) or not result.get("ok"):
            continue
        for material in result.get("materials") or []:
            if isinstance(material, dict) and material.get("id"):
                ids.add(str(material["id"]))
    return ids


class WebService:
    def __init__(
        self,
        root: Path,
        runs_dir: Path,
        llm_factory: Callable[[], tuple[LLMClient, str]] | None = None,
    ) -> None:
        self._root = Path(root)
        self._runs = RunManager(runs_dir)
        self._llm_factory = llm_factory

    # -- 基础信息 -----------------------------------------------------------

    def _model_configured(self) -> bool:
        return bool(_env("LLM_API_KEY") and _env("LLM_MODEL"))

    def meta(self) -> dict:
        available = self._llm_factory is not None or self._model_configured()
        return {
            "real_available": available,
            "model": (_env("LLM_MODEL") or None) if self._model_configured() else None,
            "max_steps_default": 10,
            "max_tool_calls": _MAX_TOOL_CALLS,
            "max_target_sec": MAX_TARGET_SEC,
            "fault_tools": list(_FAULT_TOOLS),
            "data_sets": [
                {"id": key, "label": label} for key, (label, _) in _DATA_SETS.items()
            ],
            "mock_scripts": [
                {"id": key, "label": label} for key, label in _MOCK_SCRIPTS.items()
            ],
        }

    def _catalog(self, data_set: str) -> Catalog:
        if data_set not in _DATA_SETS:
            raise ApiError(400, "UNKNOWN_DATA_SET", f"未知素材库：{data_set}")
        try:
            return load_catalog(self._root / _DATA_SETS[data_set][1])
        except DataError as exc:
            raise ApiError(500, "DATA_UNAVAILABLE", f"素材库不可用：{exc}") from None

    def materials(self, data_set: str) -> dict:
        catalog = self._catalog(data_set)
        return {
            "data_set": data_set,
            "materials": [
                {
                    "id": material.id,
                    "topic": material.topic,
                    "tags": list(material.tags),
                    "facts": list(material.facts),
                }
                for material in catalog.materials
            ],
        }

    # -- 已提交的真实运行记录 -----------------------------------------------

    def _cases(self) -> dict[str, dict]:
        path = self._root / "examples" / "cases.json"
        try:
            cases = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ApiError(500, "DATA_UNAVAILABLE", f"用例清单不可用：{exc}") from None
        return {case["name"]: case for case in cases}

    def _read_real(self, name: str, filename: str) -> str | None:
        try:
            return (self._root / "examples" / "real" / name / filename).read_text(
                encoding="utf-8"
            )
        except OSError:
            return None

    def _real_result(self, name: str) -> dict | None:
        text = self._read_real(name, "result.json")
        return json.loads(text) if text else None

    def examples(self) -> dict:
        summary_text = self._read_real("", "summary.json")
        summary = {item["name"]: item for item in json.loads(summary_text or "[]")}
        items = []
        for name, case in self._cases().items():
            row = summary.get(name, {})
            result = self._real_result(name) or {}
            items.append(
                {
                    "name": name,
                    "covers": case.get("covers"),
                    "status": row.get("status", result.get("status")),
                    "status_ok": row.get("status_ok"),
                    "path": row.get("path", []),
                    "model": row.get("model"),
                    "total_tokens": row.get("total_tokens"),
                    "title": result.get("title"),
                }
            )
        return {"examples": items}

    @staticmethod
    def _data_set_of(case: dict) -> str:
        data_dir = str(case.get("data_dir", "")).replace("\\", "/").strip("/")
        for key, (_, path) in _DATA_SETS.items():
            if path == data_dir:
                return key
        raise ApiError(500, "DATA_UNAVAILABLE", f"用例的素材目录不在白名单：{data_dir}")

    def example(self, name: str) -> dict:
        case = self._cases().get(name)
        result = self._real_result(name) if case else None
        if case is None or result is None:
            raise ApiError(404, "NOT_FOUND", f"没有这条运行记录：{name}")
        try:
            raw_input = json.loads(
                (self._root / case["input"]).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            raw_input = {}
        return {
            "name": name,
            "covers": case.get("covers"),
            "input": raw_input,
            "fault": case.get("fault"),
            "data_set": self._data_set_of(case),
            "result": result,
            "records": read_trace(self._root / "examples" / "real" / name),
            "markdown": self._read_real(name, "script.md"),
        }

    # -- 运行 ---------------------------------------------------------------

    def _build_llm(self, body: _RunBody) -> tuple[LLMClient, str]:
        if body.mode == "mock":
            if body.mock_script not in _MOCK_SCRIPTS:
                raise ApiError(
                    400, "UNKNOWN_MOCK_SCRIPT", f"未知演示脚本：{body.mock_script}"
                )
            path = self._root / "examples" / "mock_scripts" / f"{body.mock_script}.json"
            try:
                return ScriptedLLM.from_file(path), _MOCK_MODEL_NAME
            except LLMError as exc:
                raise ApiError(500, "DATA_UNAVAILABLE", str(exc)) from None

        if self._llm_factory is not None:
            return self._llm_factory()
        if not self._model_configured():
            raise ApiError(
                409,
                "MODEL_NOT_CONFIGURED",
                "还没有配置模型：请在 .env 设置 LLM_API_KEY 和 LLM_MODEL，或改用离线演示。",
            )
        model = _env("LLM_MODEL")
        try:
            llm = OpenAICompatibleLLM(
                model,
                base_url=_env("LLM_BASE_URL") or None,
                api_key=_env("LLM_API_KEY"),
            )
        except LLMError as exc:
            raise ApiError(409, "MODEL_NOT_CONFIGURED", str(exc)) from None
        return llm, model

    def start_run(self, payload: Any) -> dict:
        body = _RunBody.model_validate(payload)
        if body.data_set not in _DATA_SETS:
            raise ApiError(400, "UNKNOWN_DATA_SET", f"未知素材库：{body.data_set}")
        llm, model_name = self._build_llm(body)
        spec = RunSpec(
            raw_request=body.request.model_dump(exclude_none=True),
            llm=llm,
            mode=body.mode,
            model_name=model_name,
            data_set=body.data_set,
            data_dir=self._root / _DATA_SETS[body.data_set][1],
            fault=(
                FaultPlan(tool=body.fault.tool, times=body.fault.times)
                if body.fault
                else None
            ),
            max_steps=body.max_steps,
            max_tool_calls=_MAX_TOOL_CALLS,
        )
        try:
            return {"run_id": self._runs.start(spec)}
        except RunBusy:
            raise ApiError(
                429, "RUN_IN_PROGRESS", "已有一次运行正在进行，请等它结束后再试。"
            ) from None

    def list_runs(self) -> dict:
        return {"runs": self._runs.list_runs()}

    def run(self, run_id: str) -> dict:
        snapshot = self._runs.snapshot(run_id)
        if snapshot is None:
            raise ApiError(404, "NOT_FOUND", f"没有这次运行：{run_id}")
        return snapshot

    def run_events(self, run_id: str, last_event_id: int | None):
        if not self._runs.exists(run_id):
            raise ApiError(404, "NOT_FOUND", f"没有这次运行：{run_id}")
        return self._runs.events(run_id, last_event_id)

    # -- 校验 ---------------------------------------------------------------

    def _verify_source(self, source: _SourceBody) -> tuple[dict | None, list[dict], str]:
        if source.kind == "example":
            detail = self.example(source.id)
            return detail["result"], detail["records"], detail["data_set"]
        snapshot = self.run(source.id)
        data_set = str(snapshot["meta"].get("data_set", "default"))
        return snapshot["result"], snapshot["records"], data_set

    def verify(self, payload: Any) -> dict:
        body = _VerifyBody.model_validate(payload)
        source_result, records, data_set = self._verify_source(body.source)
        _reject_blank_fields(body.draft)
        target = (source_result or {}).get("target_duration_sec")
        if target is None:
            raise ApiError(409, "NO_TARGET", "这条记录没有目标时长，无法校验。")

        catalog = self._catalog(data_set)
        draft = ScriptDraft.model_validate(body.draft.model_dump())
        duration = estimate_duration(catalog.duration, draft, target)
        rules = check_rules(catalog, draft, _retrieved_ids(records))
        passed = duration["verdict"] == "pass" and rules["verdict"] == "pass"

        common = {
            "mode": source_result.get("mode", "real"),
            "target_duration_sec": target,
            "checks": Checks(duration=duration["verdict"], rules=rules["verdict"]),
            "risks": list(source_result.get("risks") or []),
            "steps_used": source_result.get("steps_used", 0),
            "tool_calls_used": source_result.get("tool_calls_used", 0),
        }
        if passed:
            shots = [
                FinalShot(
                    **shot.model_dump(),
                    duration_sec=estimated["duration_sec"],
                    source_ids=sorted({claim.source_id for claim in shot.claims}),
                )
                for shot, estimated in zip(draft.shots, duration["shots"], strict=True)
            ]
            result = AgentResult(
                status="completed",
                message="修改后的脚本已通过时长与规则检查。",
                title=draft.title,
                shots=shots,
                total_duration_sec=duration["total_duration_sec"],
                source_ids=sorted({sid for shot in shots for sid in shot.source_ids}),
                **common,
            )
        else:
            result = AgentResult(
                status="failed",
                message="修改后的脚本未通过检查。",
                unverified_draft=draft,
                last_estimate=duration,
                **common,
            )
        return {
            "passed": passed,
            "duration": duration,
            "rules": rules,
            "markdown": render_script_markdown(result),
            "result": result.model_dump(mode="json"),
        }
