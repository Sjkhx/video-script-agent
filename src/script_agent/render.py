"""把一次运行的结果渲染成可直接编辑的 Markdown 脚本。"""

from __future__ import annotations

from .models import AgentResult, ScriptDraft

MOCK_BANNER = "[MOCK] 本次模型决策来自预设脚本，只验证流程，不证明真实模型效果。"
UNVERIFIED_NOTE = "未通过检查，不可直接使用"

_STATUS_LABELS = {
    "completed": "已完成",
    "needs_input": "需要补充信息",
    "failed": "失败",
    "incomplete": "未完成",
}

_HEADINGS = {
    "completed": "脚本",
    "needs_input": "需要补充信息",
    "failed": "脚本生成失败",
    "incomplete": "任务未完成",
}

_CHECK_LABELS = {
    "duration": "时长",
    "rules": "品牌规则",
}

# 时长、规则检查的取值到中文说明；未知取值原样显示，便于排查。
_CHECK_VALUES = {
    "pass": "通过",
    "fail": "不通过",
    "too_long": "超出目标时长",
    "too_short": "不足目标时长",
    "error": "工具不可用",
    "not_run": "未运行",
}

_VERDICTS = {
    "pass": "通过",
    "too_long": "超出目标时长",
    "too_short": "不足目标时长",
    "fail": "不通过",
}


def _num(value: object) -> str:
    """数字去掉多余小数位；缺失时返回占位符。"""
    if value is None or isinstance(value, bool):
        return "—"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value)


def _flat(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _cell(value: object) -> str:
    """表格单元格：压平换行、转义竖线，空值用占位符。"""
    text = _flat(value).replace("|", "\\|")
    return text or "—"


def _claims_text(claims: list) -> str:
    parts = [f"{claim.source_id}：{_flat(claim.quote)}" for claim in claims]
    return "<br>".join(parts) or "—"


def _sources_text(source_ids: list[str]) -> str:
    return "、".join(source_ids) or "—"


def _check_text(result: AgentResult) -> str:
    parts = []
    for field, label in _CHECK_LABELS.items():
        value = getattr(result.checks, field, "not_run")
        parts.append(f"{label}：{_CHECK_VALUES.get(str(value), str(value))}")
    return "；".join(parts)


def _bullets(lines: list[str], items: list[str]) -> None:
    for item in items:
        lines.append(f"- {item}")


def _shots_table(shots: list) -> list[str]:
    lines = [
        "| 序号 | 画面 | 旁白 | 时长（秒） | 来源 ID | 引用原文 |",
        "|---:|---|---|---:|---|---|",
    ]
    for shot in shots:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(shot.id),
                    _cell(shot.visual),
                    _cell(shot.narration),
                    _num(shot.duration_sec),
                    _sources_text(shot.source_ids),
                    _claims_text(shot.claims),
                ]
            )
            + " |"
        )
    return lines


def _draft_table(draft: ScriptDraft) -> list[str]:
    lines = [
        "| 序号 | 画面 | 旁白 | 来源 ID | 引用原文 |",
        "|---:|---|---|---|---|",
    ]
    for shot in draft.shots:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(shot.id),
                    _cell(shot.visual),
                    _cell(shot.narration),
                    _sources_text(sorted({claim.source_id for claim in shot.claims})),
                    _claims_text(shot.claims),
                ]
            )
            + " |"
        )
    return lines


def _completed_markdown(result: AgentResult) -> list[str]:
    title = _flat(result.title) or "未命名脚本"
    lines = [f"# {title}", ""]
    _bullets(
        lines,
        [
            f"状态：{_STATUS_LABELS['completed']}",
            f"模式：{result.mode}",
            f"检查：{_check_text(result)}",
        ],
    )
    lines += ["", "## 分镜", ""]
    if result.shots:
        lines += _shots_table(result.shots)
    else:
        lines.append("没有分镜。")

    lines += ["", "## 总时长", ""]
    _bullets(
        lines,
        [
            f"预计总时长：{_num(result.total_duration_sec)} 秒",
            f"目标时长：{_num(result.target_duration_sec)} 秒",
        ],
    )

    lines += ["", "## 来源", ""]
    source_ids = sorted(set(result.source_ids))
    _bullets(lines, [f"素材 {source_id}" for source_id in source_ids] or ["无"])

    lines += ["", "## 风险", ""]
    _bullets(lines, [_flat(risk) for risk in result.risks] or ["无"])
    return lines


def _unfinished_markdown(result: AgentResult) -> list[str]:
    lines = [f"# {_HEADINGS.get(result.status, '任务未完成')}", ""]
    _bullets(
        lines,
        [
            f"状态：{_STATUS_LABELS.get(result.status, result.status)}",
            f"说明：{_flat(result.message) or '无'}",
            f"模式：{result.mode}",
            f"检查：{_check_text(result)}",
        ],
    )
    if result.target_duration_sec is not None:
        lines.append(f"- 目标时长：{_num(result.target_duration_sec)} 秒")

    lines += ["", "## 缺失信息", ""]
    _bullets(lines, [_flat(item) for item in result.missing_info] or ["无"])

    if result.last_estimate:
        verdict = result.last_estimate.get("verdict")
        total = result.last_estimate.get("total_duration_sec")
        lines += ["", "## 最近一次时长估算", ""]
        _bullets(
            lines,
            [
                f"判定：{_VERDICTS.get(str(verdict), str(verdict) if verdict else '未知')}",
                f"总时长：{_num(total)} 秒",
            ],
        )

    if result.unverified_draft is not None:
        draft = result.unverified_draft
        lines += [
            "",
            f"## 草稿（{UNVERIFIED_NOTE}）",
            "",
            f"标题：{_flat(draft.title)}",
            "",
        ]
        lines += _draft_table(draft)
    return lines


def render_script_markdown(result: AgentResult) -> str:
    """按状态渲染 Markdown；Mock 模式在开头标明边界。"""
    if result.status == "completed":
        lines = _completed_markdown(result)
    else:
        lines = _unfinished_markdown(result)
    if result.mode == "mock":
        lines = [MOCK_BANNER, "", *lines]
    return "\n".join(lines).rstrip("\n") + "\n"
