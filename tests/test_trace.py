import json

import pytest

from script_agent.models import AgentResult
from script_agent.trace import TraceRecorder, summarize_observation


@pytest.mark.parametrize("action,observation,expected", [
    ("search_materials", {"ok": True, "count": 1, "materials": [{"id": "P01"}]}, "命中 1 条: P01"),
    ("search_materials", {"ok": True, "count": 0, "materials": []}, "命中 0 条"),
    ("estimate_duration", {"ok": True, "total_duration_sec": 37.5, "target_duration_sec": 30.0, "verdict": "too_long", "overflow_sec": 7.5, "shortfall_sec": 0.0}, "总时长 37.5s，目标 30s，判定 too_long，超出 7.5s"),
    ("check_rules", {"ok": True, "verdict": "pass", "violations": []}, "判定 pass"),
    ("check_rules", {"ok": True, "verdict": "fail", "violations": [{"code": "MISSING_CLOSING_SLOGAN"}, {"code": "UNSUPPORTED_TERM"}]}, "判定 fail: MISSING_CLOSING_SLOGAN, UNSUPPORTED_TERM"),
])
def test_summaries(action, observation, expected):
    assert summarize_observation(action, observation) == expected


def test_error_summary_contains_code():
    summary = summarize_observation("check_rules", {"ok": False, "error": {"code": "TOOL_UNAVAILABLE", "message": "暂不可用"}})
    assert "TOOL_UNAVAILABLE" in summary


@pytest.mark.parametrize("action", [
    "search_materials", "estimate_duration", "check_rules",
    "submit_script", "ask_user", "report_failure", "unknown_tool",
])
@pytest.mark.parametrize("observation", [
    {}, {"ok": True}, {"ok": False}, {"ok": False, "error": "boom"},
    {"ok": True, "count": None, "materials": None},
    {"ok": True, "verdict": "fail", "violations": [{}]},
])
def test_missing_fields_never_raise(action, observation):
    assert isinstance(summarize_observation(action, observation), str)


def test_finish_backfills_next_action_and_writes_files(tmp_path):
    t = TraceRecorder(tmp_path, mode="mock", model="scripted", request={"topic": "字幕"}, fault=None, max_steps=10, max_tool_calls=20)
    for seq, action in enumerate(["search_materials", "submit_script"], 1):
        t.step(round=seq, seq=seq, action=action, args={}, observation={"ok": True, "count": 0, "materials": []}, decision_note="依据", injected_fault=False, usage={"prompt_tokens": 1, "completion_tokens": 1})
    t.finish(AgentResult(status="completed", message="完成", mode="mock", steps_used=2, tool_calls_used=2))
    lines = [json.loads(x) for x in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [x["type"] for x in lines] == ["run_start", "step", "step", "run_end"]
    assert lines[1]["next_action"] == "submit_script"
    assert lines[2]["next_action"] == "END:completed"
    assert lines[3]["total_tokens"] == 4
    assert "search_materials" in (tmp_path / "trace.md").read_text(encoding="utf-8")


def test_run_start_and_note_records(tmp_path):
    t = TraceRecorder(
        tmp_path, mode="real", model="m", request={"topic": "字幕", "target_duration_sec": 30.0},
        fault={"tool": "estimate_duration", "times": 1}, max_steps=10, max_tool_calls=20,
    )
    t.step(round=1, seq=1, action="search_materials", args={"query": "字幕"}, observation={"ok": True, "count": 0, "materials": []}, decision_note="先检索", injected_fault=False, usage={"prompt_tokens": 1, "completion_tokens": 1})
    t.note(round=2, event="no_action", detail="模型只回复了文字")
    t.finish(AgentResult(status="incomplete", message="达到步数上限", mode="real", steps_used=2, tool_calls_used=1))
    lines = [json.loads(x) for x in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    start = lines[0]
    assert start["type"] == "run_start"
    assert start["run_id"] and start["started_at"]
    assert start["mode"] == "real" and start["model"] == "m"
    assert start["request"] == {"topic": "字幕", "target_duration_sec": 30.0}
    assert start["fault"] == {"tool": "estimate_duration", "times": 1}
    assert (start["max_steps"], start["max_tool_calls"]) == (10, 20)
    note = [x for x in lines if x["type"] == "note"][0]
    assert (note["round"], note["event"], note["detail"]) == (2, "no_action", "模型只回复了文字")
    assert lines[-1]["status"] == "incomplete"


def test_usage_is_counted_once_per_round(tmp_path):
    t = TraceRecorder(tmp_path, mode="mock", model="scripted", request={}, fault=None, max_steps=10, max_tool_calls=20)
    usage = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
    # 同一轮的两次工具调用共享同一份 usage，只能计一次。
    for seq in (1, 2):
        t.step(round=1, seq=seq, action="search_materials", args={}, observation={"ok": True, "count": 0, "materials": []}, decision_note="同轮", injected_fault=False, usage=usage)
    t.step(round=2, seq=3, action="search_materials", args={}, observation={"ok": True, "count": 0, "materials": []}, decision_note="下一轮", injected_fault=False, usage={"prompt_tokens": 1, "completion_tokens": 1})
    t.finish(AgentResult(status="completed", message="完成", mode="mock", steps_used=2, tool_calls_used=3))
    lines = [json.loads(x) for x in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines[-1]["total_tokens"] == 7


def test_trace_omits_model_internal_fields_and_keys(tmp_path):
    t = TraceRecorder(tmp_path, mode="mock", model="scripted", request={"topic": "字幕"}, fault=None, max_steps=10, max_tool_calls=20)
    t.step(
        round=1,
        seq=1,
        action="search_materials",
        args={"query": "字幕", "reasoning_content": "内部推理", "api_key": "sk-test-should-not-leak"},
        observation={"ok": True, "count": 1, "materials": [{"id": "P01"}], "reasoning_content": "内部推理"},
        decision_note="看到素材",
        injected_fault=False,
        usage={"prompt_tokens": 1, "completion_tokens": 1},
    )
    t.finish(AgentResult(status="completed", message="完成", mode="mock", steps_used=1, tool_calls_used=1))
    text = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    assert "reasoning_content" not in text and "内部推理" not in text
    assert "sk-test-should-not-leak" not in text
    assert "看到素材" in text


def test_trace_md_shows_only_title_and_shot_count_for_script_args(tmp_path):
    t = TraceRecorder(tmp_path, mode="mock", model="scripted", request={}, fault=None, max_steps=10, max_tool_calls=20)
    shots = [{"id": i, "visual": "画面内容不该出现", "narration": "旁白内容不该出现"} for i in range(1, 5)]
    t.step(round=1, seq=1, action="estimate_duration", args={"title": "静音也能看懂", "shots": shots}, observation={"ok": True, "total_duration_sec": 30.0, "target_duration_sec": 30.0, "verdict": "pass", "overflow_sec": 0.0, "shortfall_sec": 0.0}, decision_note="初稿", injected_fault=False, usage={})
    t.finish(AgentResult(status="completed", message="完成", mode="mock", steps_used=1, tool_calls_used=1))
    md = (tmp_path / "trace.md").read_text(encoding="utf-8")
    assert all(column in md for column in ["步骤", "动作", "关键参数", "返回摘要", "下一步", "决策依据"])
    assert "静音也能看懂" in md and "分镜" in md and "4" in md
    assert "画面内容不该出现" not in md and "旁白内容不该出现" not in md


def test_result_summary_is_redacted_in_jsonl_and_markdown(tmp_path):
    key = "sk-summary-should-not-leak"
    t = TraceRecorder(tmp_path, mode="mock", model="scripted", request={}, fault=None, max_steps=10, max_tool_calls=20)
    t.step(
        round=1,
        seq=1,
        action="check_rules",
        args={},
        observation={"ok": False, "error": {"code": "TOOL_UNAVAILABLE", "message": f"上游返回 {key}"}},
        decision_note="工具失败",
        injected_fault=False,
        usage={},
    )
    t.finish(AgentResult(status="failed", message="失败", mode="mock", steps_used=1, tool_calls_used=1))
    jsonl = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    md = (tmp_path / "trace.md").read_text(encoding="utf-8")
    assert key not in jsonl and key not in md
    assert "TOOL_UNAVAILABLE" in jsonl and "TOOL_UNAVAILABLE" in md


@pytest.mark.parametrize("name", [
    "clientSecret", "x-api-key", "OPENAI_API_KEY", "authorization",
])
def test_prefixed_and_camel_case_key_names_are_dropped(tmp_path, name):
    value = "plain-credential-value-with-no-prefix"
    t = TraceRecorder(tmp_path, mode="mock", model="scripted", request={}, fault=None, max_steps=10, max_tool_calls=20)
    t.step(
        round=1,
        seq=1,
        action="search_materials",
        args={"query": "字幕", name: value},
        observation={"ok": True, "count": 1, "materials": [{"id": "P01"}], name: value},
        decision_note="检索",
        injected_fault=False,
        usage={},
    )
    t.finish(AgentResult(status="completed", message="完成", mode="mock", steps_used=1, tool_calls_used=1))
    jsonl = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    assert value not in jsonl


def test_note_redacts_caller_supplied_secret(tmp_path):
    secret = "my-custom-credential-9f8e7d"
    t = TraceRecorder(
        tmp_path, mode="real", model="m", request={}, fault=None,
        max_steps=10, max_tool_calls=20, secrets=[secret],
    )
    t.note(round=1, event="llm_retry", detail=f"请求携带 {secret} 被拒绝")
    t.finish(AgentResult(status="failed", message="失败", mode="real", steps_used=1, tool_calls_used=0))
    jsonl = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    md = (tmp_path / "trace.md").read_text(encoding="utf-8")
    assert secret not in jsonl and secret not in md
    assert "llm_retry" in jsonl
    assert "被拒绝" in md


def test_token_usage_is_not_redacted_by_key_name_filter(tmp_path):
    t = TraceRecorder(tmp_path, mode="mock", model="scripted", request={}, fault=None, max_steps=10, max_tool_calls=20)
    t.step(
        round=1,
        seq=1,
        action="search_materials",
        args={},
        observation={"ok": True, "count": 0, "materials": []},
        decision_note="无素材",
        injected_fault=False,
        usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    )
    t.finish(AgentResult(status="completed", message="完成", mode="mock", steps_used=1, tool_calls_used=1))
    lines = [json.loads(x) for x in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines[1]["usage"] == {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
    assert lines[-1]["total_tokens"] == 5


def test_non_dict_args_raw_string_is_redacted(tmp_path):
    key = "sk-raw-args-should-not-leak"
    t = TraceRecorder(tmp_path, mode="mock", model="scripted", request={}, fault=None, max_steps=10, max_tool_calls=20)
    t.step(
        round=1,
        seq=1,
        action="search_materials",
        args=f"not-an-object {key}",
        observation={"ok": True, "count": 0, "materials": []},
        decision_note="参数非法",
        injected_fault=False,
        usage={},
    )
    t.finish(AgentResult(status="failed", message="失败", mode="mock", steps_used=1, tool_calls_used=1))
    jsonl = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    md = (tmp_path / "trace.md").read_text(encoding="utf-8")
    assert key not in jsonl and key not in md


def test_note_redacts_secret_straddling_clip_boundary(tmp_path):
    secret = "plainboundarysecret123456"
    # 让密钥前半段落在 300 字截断点之内，后半段被切掉；先截后脱敏会漏出残片。
    filler = "填" * (300 - 5)
    t = TraceRecorder(
        tmp_path, mode="real", model="m", request={}, fault=None,
        max_steps=10, max_tool_calls=20, secrets=[secret],
    )
    t.note(round=1, event="boundary", detail=filler + secret)
    t.finish(AgentResult(status="failed", message="失败", mode="real", steps_used=1, tool_calls_used=0))
    jsonl = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    # 不能出现密钥的任何前 4 字符片段。
    assert secret[:4] not in jsonl
    assert secret not in jsonl


def test_bare_string_secrets_is_treated_as_one_literal(tmp_path):
    secret = "single-string-secret"
    t = TraceRecorder(
        tmp_path, mode="real", model="m", request={}, fault=None,
        max_steps=10, max_tool_calls=20, secrets=secret,
    )
    t.note(round=1, event="string_secret", detail=f"请求使用 {secret} 调用失败")
    t.finish(AgentResult(status="failed", message="失败", mode="real", steps_used=1, tool_calls_used=0))
    jsonl = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    md = (tmp_path / "trace.md").read_text(encoding="utf-8")
    assert secret not in jsonl and secret not in md
    # 周围文本不能被逐字符打星。
    assert "请求使用" in jsonl and "调用失败" in jsonl
    assert "h***" not in jsonl and "*" * 5 not in jsonl


def test_error_message_secret_is_redacted_even_within_length_limit(tmp_path):
    """错误信息没超长也要脱敏：不走截断分支不代表安全。"""
    secret = "plainerrormessagesecret9876"
    t = TraceRecorder(
        tmp_path, mode="real", model="m", request={}, fault=None,
        max_steps=10, max_tool_calls=20, secrets=[secret],
    )
    t.step(
        round=1, seq=1, action="check_rules", args={},
        observation={"ok": False, "error": {"code": "TOOL_EXCEPTION", "message": f"内部错误 {secret}"}},
        decision_note="工具异常", injected_fault=False, usage={},
    )
    t.finish(AgentResult(status="failed", message="失败", mode="real", steps_used=1, tool_calls_used=1))
    jsonl = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    md = (tmp_path / "trace.md").read_text(encoding="utf-8")
    assert secret not in jsonl and secret not in md
    assert "TOOL_EXCEPTION" in jsonl


def test_summary_secret_straddling_clip_boundary_is_redacted(tmp_path):
    """summary 内部先截断，密钥跨 80 字边界时也不能漏出前段。"""
    secret = "zzboundarysecret54321"
    t = TraceRecorder(
        tmp_path, mode="real", model="m", request={}, fault=None,
        max_steps=10, max_tool_calls=20, secrets=secret,
    )
    t.step(
        round=1, seq=1, action="something_else", args={},
        observation={"ok": True, "message": "填" * 78 + secret},
        decision_note="其它", injected_fault=False, usage={},
    )
    t.finish(AgentResult(status="completed", message="完成", mode="real", steps_used=1, tool_calls_used=1))
    jsonl = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    assert secret[:6] not in jsonl
