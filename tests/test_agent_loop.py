import json

import pytest

from helpers import DATA_DIR, SLOGAN, call, fit_draft, round_of
from script_agent.agent import run_agent
from script_agent.llm import ScriptedLLM
from script_agent.models import normalize_request
from script_agent.prompts import NUDGE, SYSTEM_PROMPT
from script_agent.registry import FaultPlan, ToolRegistry
from script_agent.trace import TraceRecorder

def run_scripted(tmp_path, steps, raw=None, fault=None, max_steps=10, max_tool_calls=20):
    request = normalize_request(raw or {"topic": "字幕功能", "target_duration_sec": 30})
    llm = ScriptedLLM(steps)
    registry = ToolRegistry(request, DATA_DIR, fault)
    trace = TraceRecorder(tmp_path, mode="mock", model="scripted", request=request.model_dump(), fault=None, max_steps=max_steps, max_tool_calls=max_tool_calls)
    result = run_agent(request, llm, registry, trace, mode="mock", max_steps=max_steps, max_tool_calls=max_tool_calls)
    lines = [json.loads(x) for x in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    return result, lines, llm

def steps_of(lines):
    return [x for x in lines if x["type"] == "step"]

def search(query="字幕"):
    return round_of(call("search_materials", query=query))

def verify(draft):
    return round_of(call("estimate_duration", **draft), call("check_rules", **draft))

def submit(draft):
    return round_of(call("submit_script", **draft, risks=[]))

def test_normal_path(tmp_path):
    d = fit_draft()
    result, lines, _ = run_scripted(tmp_path, [search(), verify(d), submit(d)])
    assert result.status == "completed"
    assert result.source_ids == ["P01"] and result.total_duration_sec == 30.0
    assert (result.steps_used, result.tool_calls_used) == (3, 4)
    assert [s["action"] for s in steps_of(lines)] == ["search_materials", "estimate_duration", "check_rules", "submit_script"]
    assert steps_of(lines)[-1]["next_action"] == "END:completed"
    assert all(s["decision_note"] for s in steps_of(lines))
    assert lines[-1]["status"] == "completed"

def test_missing_info_path(tmp_path):
    steps = [round_of(call("ask_user", missing_fields=["target_duration_sec"], questions=["目标时长是多少秒？"], reason="缺目标时长"))]
    result, _, llm = run_scripted(tmp_path, steps, raw={"topic": "字幕功能"})
    assert result.status == "needs_input" and result.shots is None and result.total_duration_sec is None
    assert "target_duration_sec" in llm.seen_messages[0][1]["content"]

def test_invalid_target_is_visible_to_model(tmp_path):
    steps = [round_of(call("ask_user", missing_fields=["target_duration_sec"], questions=["请给出秒数"], reason="时长无效"))]
    _, _, llm = run_scripted(tmp_path, steps, raw={"topic": "字幕功能", "target_duration_sec": "三十秒"})
    assert "invalid_fields" in llm.seen_messages[0][1]["content"]

def test_no_materials_path(tmp_path):
    steps = [search("直播"), search("推流"), round_of(call("ask_user", missing_fields=["materials"], questions=["请补充直播素材"], reason="检索无结果"))]
    result, lines, _ = run_scripted(tmp_path, steps)
    assert result.status == "needs_input" and result.missing_info == ["materials"]
    assert [s["args"]["query"] for s in steps_of(lines)[:2]] == ["直播", "推流"]
    assert all(s["result"]["count"] == 0 for s in steps_of(lines)[:2])

def test_query_rewrite_path(tmp_path):
    d = fit_draft()
    result, lines, _ = run_scripted(tmp_path, [search("让视频自动出现文字"), search("字幕"), verify(d), submit(d)])
    assert result.status == "completed"
    assert steps_of(lines)[0]["result"]["count"] == 0 and steps_of(lines)[1]["result"]["count"] == 1

def test_tool_failure_then_recover(tmp_path):
    d = fit_draft()
    steps = [search(), verify(d), round_of(call("estimate_duration", **d)), submit(d)]
    result, lines, _ = run_scripted(tmp_path, steps, fault=FaultPlan("estimate_duration", 1))
    assert result.status == "completed"
    assert any(s["injected_fault"] for s in steps_of(lines))

def test_permanent_tool_failure_is_reported(tmp_path):
    d = fit_draft()
    steps = [search(), verify(d), round_of(call("check_rules", **d)), round_of(call("report_failure", reason="规则工具不可用", failed_tools=["check_rules"]))]
    result, _, _ = run_scripted(tmp_path, steps, fault=FaultPlan("check_rules", -1))
    assert result.status == "failed" and result.checks.rules == "error"
    assert result.shots is None and result.unverified_draft is not None

def test_search_failure_produces_no_script(tmp_path):
    steps = [search(), search(), round_of(call("report_failure", reason="素材检索不可用", failed_tools=["search_materials"]))]
    result, _, _ = run_scripted(tmp_path, steps, fault=FaultPlan("search_materials", -1))
    assert result.status == "failed" and result.shots is None and result.source_ids == []

def test_over_duration_then_fixed(tmp_path):
    long_draft, fixed = fit_draft(5), fit_draft(4, 26)
    result, lines, _ = run_scripted(tmp_path, [search(), verify(long_draft), verify(fixed), submit(fixed)])
    assert result.status == "completed" and result.total_duration_sec == 28.0
    estimates = [s["result"]["verdict"] for s in steps_of(lines) if s["action"] == "estimate_duration"]
    assert estimates == ["too_long", "pass"]

def test_over_duration_cannot_be_met(tmp_path):
    d = fit_draft(2, 15)
    steps = [search(), verify(d), round_of(call("report_failure", reason="3 秒放不下品牌语", unmet_requirements=["目标时长 3 秒"]))]
    result, _, _ = run_scripted(tmp_path, steps, raw={"topic": "字幕功能", "target_duration_sec": 3})
    assert result.status == "failed" and result.shots is None and result.total_duration_sec is None
    assert result.last_estimate["verdict"] == "too_long"
    assert result.target_duration_sec == 3.0

def test_gate_rejection_returns_to_model(tmp_path):
    steps = [submit(fit_draft()), round_of(call("report_failure", reason="未通过检查"))]
    result, lines, _ = run_scripted(tmp_path, steps)
    assert result.status == "failed"
    assert steps_of(lines)[0]["result"]["error"]["code"] == "GATE_REJECTED"

def test_invalid_json_arguments_recover(tmp_path):
    d = fit_draft()
    bad = {"tool_calls": [{"name": "search_materials", "arguments": "{bad"}]}
    result, lines, _ = run_scripted(tmp_path, [bad, search(), verify(d), submit(d)])
    assert result.status == "completed"
    assert steps_of(lines)[0]["result"]["error"]["code"] == "INVALID_ARGS"

def test_text_only_reply_is_not_completion(tmp_path):
    result, lines, llm = run_scripted(tmp_path, [{"content": "脚本已完成，总时长 28 秒"}] * 3, max_steps=3)
    assert result.status == "incomplete" and result.shots is None and result.total_duration_sec is None
    assert sum(1 for x in lines if x["type"] == "note") == 3
    assert any(m.get("content") == NUDGE for m in llm.seen_messages[1])

def test_max_steps_returns_incomplete(tmp_path):
    result, _, _ = run_scripted(tmp_path, [search()] * 5, max_steps=3)
    assert result.status == "incomplete" and result.steps_used == 3
    assert "步数上限" in result.message

def test_max_tool_calls_returns_incomplete(tmp_path):
    many = round_of(*[call("search_materials", query="字幕") for _ in range(5)])
    result, _, _ = run_scripted(tmp_path, [many], max_tool_calls=2)
    assert result.status == "incomplete" and result.tool_calls_used == 2

def test_llm_error_is_reported(tmp_path):
    result, lines, _ = run_scripted(tmp_path, [{"raise": "401 unauthorized"}])
    assert result.status == "failed" and result.message.startswith("模型调用失败")
    assert lines[-1]["type"] == "run_end"

def test_message_protocol_for_parallel_calls(tmp_path):
    d = fit_draft()
    _, _, llm = run_scripted(tmp_path, [search(), verify(d), submit(d)])
    third = llm.seen_messages[2]
    assert third[-3]["role"] == "assistant" and len(third[-3]["tool_calls"]) == 2
    assert [m["tool_call_id"] for m in third[-2:]] == [c["id"] for c in third[-3]["tool_calls"]]

def test_prompt_does_not_leak_tool_only_knowledge():
    assert SLOGAN not in SYSTEM_PROMPT
    assert "每秒" not in SYSTEM_PROMPT
