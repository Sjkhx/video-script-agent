import json

import pytest

from helpers import DATA_DIR, args, fit_draft
from script_agent.models import ScriptDraft, draft_hash, normalize_request
from script_agent.registry import FaultPlan, ToolRegistry

REQUEST = {"topic": "字幕", "target_duration_sec": 30}


def make(fault=None, raw=REQUEST, data_dir=DATA_DIR):
    return ToolRegistry(normalize_request(raw), data_dir, fault)


def passed(registry, draft):
    registry.execute("search_materials", args(query="字幕"))
    registry.execute("estimate_duration", args(**draft))
    registry.execute("check_rules", args(**draft))


def test_schemas_expose_all_tools_with_required_decision_note():
    schemas = make().schemas()
    assert {s["function"]["name"] for s in schemas} == {
        "search_materials",
        "estimate_duration",
        "check_rules",
        "submit_script",
        "ask_user",
        "report_failure",
    }
    assert all("decision_note" in s["function"]["parameters"]["required"] for s in schemas)
    assert "$ref" not in json.dumps(schemas)


def test_unknown_tool_and_invalid_args_do_not_raise():
    r = make()
    assert r.execute("delete_everything", "{}").observation["error"]["code"] == "UNKNOWN_TOOL"
    bad = r.execute("search_materials", "{bad")
    assert bad.observation["error"]["code"] == "INVALID_ARGS" and bad.terminal is None
    assert bad.args == {"_raw": "{bad"}
    assert r.execute("search_materials", json.dumps({"query": "字幕"})).observation["error"]["code"] == "INVALID_ARGS"  # 缺 decision_note
    assert r.execute("estimate_duration", args(title="t", shots=[])).observation["error"]["code"] == "INVALID_ARGS"
    assert r.execute("search_materials", args(query=" ， ")).observation["error"]["code"] == "INVALID_ARGS"


def test_fault_once_then_recovers():
    r = make(FaultPlan("estimate_duration", 1))
    first = r.execute("estimate_duration", args(**fit_draft()))
    assert first.observation["error"]["code"] == "TOOL_UNAVAILABLE"
    assert first.observation["error"]["retries_left"] == 1
    assert first.injected_fault is True
    assert "注入" not in first.observation["error"]["message"]
    second = r.execute("estimate_duration", args(**fit_draft()))
    assert second.observation["verdict"] == "pass" and second.injected_fault is False


def test_permanent_fault_exhausts_retries():
    r = make(FaultPlan("check_rules", -1))
    left = [r.execute("check_rules", args(**fit_draft())).observation["error"]["retries_left"] for _ in range(3)]
    assert left == [1, 0, 0]


def test_missing_data_is_tool_failure(tmp_path):
    r = make(data_dir=tmp_path / "nope")
    out = r.execute("search_materials", args(query="字幕"))
    assert out.observation["error"]["code"] == "DATA_UNAVAILABLE"
    assert out.observation["error"]["retries_left"] == 1


def test_estimate_without_target():
    out = make(raw={"topic": "字幕"}).execute("estimate_duration", args(**fit_draft()))
    assert out.observation["error"]["code"] == "MISSING_TARGET"


def test_submit_without_checks_is_rejected():
    out = make().execute("submit_script", args(**fit_draft(), risks=[]))
    assert out.terminal is None
    assert out.observation["error"]["code"] == "GATE_REJECTED"
    assert any("duration" in reason for reason in out.observation["error"]["reasons"])
    assert any("rules" in reason for reason in out.observation["error"]["reasons"])


def test_submit_after_checks_uses_tool_durations():
    r, draft = make(), fit_draft()
    passed(r, draft)
    tampered = json.loads(json.dumps(draft))
    tampered["shots"][0]["duration_sec"] = 1
    out = r.execute("submit_script", args(**tampered, risks=["测试风险"]))
    assert out.terminal == "completed"
    result = r.build_result("completed", mode="mock", steps_used=3, tool_calls_used=4)
    assert result.total_duration_sec == 30.0
    assert [s.duration_sec for s in result.shots] == [7.5, 7.5, 7.5, 7.5]
    assert result.shots[0].source_ids == ["P01"] and result.source_ids == ["P01"]
    assert result.checks.duration == "pass" and result.checks.rules == "pass"
    assert "测试风险" in result.risks and len(result.risks) == 4  # 模型 1 条 + 假设 3 条


def test_changing_draft_after_checks_is_rejected():
    r, draft = make(), fit_draft()
    passed(r, draft)
    changed = fit_draft()
    changed["shots"][1]["narration"] = "嗯" * 27 + "哦"
    assert r.execute("submit_script", args(**changed, risks=[])).observation["error"]["code"] == "GATE_REJECTED"


def test_too_long_draft_cannot_be_submitted():
    r, draft = make(), fit_draft(5)
    passed(r, draft)
    assert r.execute("submit_script", args(**draft, risks=[])).terminal is None


def test_tool_failure_never_counts_as_pass():
    r, draft = make(FaultPlan("check_rules", -1)), fit_draft()
    passed(r, draft)
    assert r.execute("submit_script", args(**draft, risks=[])).terminal is None
    r.execute("report_failure", args(reason="规则工具不可用", failed_tools=["check_rules"]))
    result = r.build_result("failed", mode="mock", steps_used=4, tool_calls_used=5)
    assert result.checks.rules == "error" and result.shots is None
    assert result.unverified_draft is not None


def test_missing_required_blocks_submission_even_with_checks():
    r = make(raw={"target_duration_sec": 30})
    draft = fit_draft()
    passed(r, draft)
    out = r.execute("submit_script", args(**draft, risks=[]))
    assert out.terminal is None and any("topic" in x for x in out.observation["error"]["reasons"])


def test_ask_user_builds_needs_input():
    r = make(raw={"topic": "字幕"})
    out = r.execute("ask_user", args(missing_fields=["target_duration_sec"], questions=["目标时长是多少秒？"], reason="缺目标时长"))
    assert out.terminal == "needs_input"
    result = r.build_result("needs_input", mode="mock", steps_used=1, tool_calls_used=1)
    assert result.missing_info == ["target_duration_sec"] and result.shots is None and result.total_duration_sec is None
    assert "目标时长是多少秒" in result.message


@pytest.mark.parametrize("top_k", [0, 11, -1])
def test_top_k_out_of_range_is_invalid_args(top_k):
    out = make().execute("search_materials", args(query="字幕", top_k=top_k))
    assert out.observation["error"]["code"] == "INVALID_ARGS"


def test_top_k_in_range_is_accepted():
    out = make().execute("search_materials", args(query="字幕", top_k=10))
    assert out.observation["ok"] is True and out.args["top_k"] == 10


def test_decision_note_length_is_not_validated():
    note = "观" * 45
    out = make().execute("search_materials", args(query="字幕", decision_note=note))
    assert out.observation["ok"] is True and out.decision_note == note
    assert "decision_note" not in out.args


def test_last_estimate_belongs_to_the_reported_draft():
    """估算过的草稿和最终报告的草稿不是同一份时，不能把前者的时长挂上去。"""
    r = make()
    checked = fit_draft()
    passed(r, checked)
    # 换成另一份草稿只做规则检查，last_draft 随之变成这一份。
    changed = fit_draft()
    changed["shots"][1]["narration"] = "嗯" * 27 + "哦"
    r.execute("check_rules", args(**changed))
    result = r.build_result("failed", mode="mock", steps_used=3, tool_calls_used=4)
    assert result.unverified_draft is not None
    assert draft_hash(result.unverified_draft) != draft_hash(
        ScriptDraft.model_validate(checked)
    )
    assert result.last_estimate is None
