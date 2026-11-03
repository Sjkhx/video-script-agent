import json

from helpers import DATA_DIR, call, round_of
from script_agent.app import run_once
from script_agent.llm import ScriptedLLM
from script_agent.models import AgentResult
from script_agent.trace import TraceRecorder

def make(tmp_path, listener):
    return TraceRecorder(tmp_path, mode="mock", model="scripted", request={"topic": "字幕"}, fault=None, max_steps=10, max_tool_calls=20, listener=listener)

def add_step(trace):
    trace.step(round=1, seq=1, action="search_materials", args={"query": "字幕"}, observation={"ok": True, "count": 0, "materials": []}, decision_note="依据", injected_fault=False, usage={"prompt_tokens": 1, "completion_tokens": 1})

def test_listener_receives_all_record_types(tmp_path):
    seen = []
    trace = make(tmp_path, seen.append)
    add_step(trace)
    trace.note(round=2, event="no_action", detail="没有调用工具")
    trace.finish(AgentResult(status="failed", message="m", mode="mock"))
    assert [r["type"] for r in seen] == ["run_start", "step", "note", "run_end"]
    assert seen[1]["result_summary"] == "命中 0 条"
    assert seen[3]["status"] == "failed"

def test_listener_gets_copies(tmp_path):
    seen = []
    trace = make(tmp_path, seen.append)
    add_step(trace)
    seen[1]["action"] = "tampered"
    trace.finish(AgentResult(status="failed", message="m", mode="mock"))
    assert "tampered" not in (tmp_path / "trace.jsonl").read_text(encoding="utf-8")

def test_listener_errors_do_not_break_the_run(tmp_path):
    def boom(_):
        raise RuntimeError("boom")
    trace = make(tmp_path, boom)
    add_step(trace)
    trace.finish(AgentResult(status="failed", message="m", mode="mock"))
    lines = (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["type"] == "run_end"

def test_run_once_forwards_listener(tmp_path):
    seen = []
    steps = [round_of(call("ask_user", missing_fields=["other"], questions=["？"], reason="测试"))]
    result = run_once({"topic": "字幕"}, ScriptedLLM(steps), mode="mock", model_name="scripted", data_dir=DATA_DIR, fault=None, max_steps=3, max_tool_calls=5, out_dir=tmp_path, listener=seen.append)
    assert result.status == "needs_input"
    assert [r["type"] for r in seen] == ["run_start", "step", "run_end"]
