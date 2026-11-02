import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import call, fit_draft, round_of
from script_agent.cli import main
from script_agent.models import AgentResult, ScriptDraft
from script_agent.render import render_script_markdown

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "examples/inputs/01_normal.json"
MOCK = ROOT / "examples/mock_scripts/01_normal.json"


def write_mock(tmp_path, steps):
    path = tmp_path / "mock.json"
    path.write_text(json.dumps({"steps": steps}, ensure_ascii=False), encoding="utf-8")
    return path


def read_jsonl(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("script", ["01_normal.json", "06_over_duration_fixed.json"])
def test_mock_scripts_complete_and_write_outputs(tmp_path, script):
    code = main(["--input", str(INPUT), "--mock-script", str(ROOT / "examples/mock_scripts" / script), "--out-dir", str(tmp_path)])
    assert code == 0
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "completed" and result["mode"] == "mock"
    assert "P01" in result["source_ids"]
    assert result["total_duration_sec"] == pytest.approx(sum(s["duration_sec"] for s in result["shots"]))
    for name in ["script.md", "trace.jsonl", "trace.md"]:
        assert (tmp_path / name).exists()
    assert "[MOCK]" in (tmp_path / "script.md").read_text(encoding="utf-8")


def test_second_mock_shows_over_duration(tmp_path):
    main(["--input", str(INPUT), "--mock-script", str(ROOT / "examples/mock_scripts/06_over_duration_fixed.json"), "--out-dir", str(tmp_path)])
    lines = [json.loads(x) for x in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    verdicts = [x["result"]["verdict"] for x in lines if x["type"] == "step" and x["action"] == "estimate_duration" and x["result"]["ok"]]
    assert verdicts[0] == "too_long" and verdicts[-1] == "pass"


def test_missing_model_config_never_falls_back_to_mock(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "")
    code = main(["--input", str(INPUT), "--out-dir", str(tmp_path / "out")])
    assert code == 2
    assert "LLM_API_KEY" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("argv", [
    ["--input", "no_such_file.json"],
    ["--input", str(INPUT), "--fail-tool", "delete_everything"],
    ["--input", str(INPUT), "--max-steps", "0"],
])
def test_usage_errors_exit_2(argv, tmp_path):
    with_mock = [*argv, "--mock-script", str(MOCK), "--out-dir", str(tmp_path)]
    try:
        assert main(with_mock) == 2
    except SystemExit as e:  # argparse 对 choices 错误会抛 SystemExit
        assert e.code == 2


def test_overrides_apply(tmp_path):
    steps = [round_of(call("ask_user", missing_fields=["other"], questions=["确认？"], reason="测试"))]
    code = main(["--input", str(INPUT), "--target", "15", "--mock-script", str(write_mock(tmp_path, steps)), "--out-dir", str(tmp_path / "out")])
    assert code == 0
    lines = (tmp_path / "out" / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["request"]["target_duration_sec"] == 15.0


def test_incomplete_exit_code(tmp_path):
    steps = [round_of(call("search_materials", query="字幕"))] * 3
    code = main(["--input", str(INPUT), "--max-steps", "2", "--mock-script", str(write_mock(tmp_path, steps)), "--out-dir", str(tmp_path / "out")])
    assert code == 1
    assert json.loads((tmp_path / "out" / "result.json").read_text(encoding="utf-8"))["status"] == "incomplete"


def test_gbk_console_does_not_crash(tmp_path):
    draft = fit_draft()
    for shot in draft["shots"]:
        shot["visual"] = "😀画面"
    steps = [
        round_of(call("search_materials", query="字幕")),
        round_of(call("estimate_duration", **draft), call("check_rules", **draft)),
        round_of(call("submit_script", **draft, risks=[])),
    ]
    proc = subprocess.run(
        [sys.executable, "-m", "script_agent", "--input", str(INPUT), "--mock-script", str(write_mock(tmp_path, steps)), "--out-dir", str(tmp_path / "out")],
        env={**os.environ, "PYTHONIOENCODING": "gbk"}, capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert b"UnicodeEncodeError" not in proc.stderr


def test_api_key_is_not_written_anywhere(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test-should-not-leak")
    main(["--input", str(INPUT), "--mock-script", str(MOCK), "--out-dir", str(tmp_path)])
    for path in tmp_path.iterdir():
        assert "sk-test-should-not-leak" not in path.read_text(encoding="utf-8")


def test_failed_result_markdown_flags_unverified_draft():
    result = AgentResult(status="failed", message="规则工具不可用", mode="real", unverified_draft=ScriptDraft.model_validate(fit_draft()))
    assert "未通过检查，不可直接使用" in render_script_markdown(result)


def test_fault_plan_is_serialized_into_trace(tmp_path):
    """FaultPlan 必须按字典写入 trace.jsonl，不能因为类型不符写成 null。"""
    draft = fit_draft()
    steps = [
        round_of(call("search_materials", query="字幕")),
        round_of(call("estimate_duration", **draft)),
        round_of(call("estimate_duration", **draft)),
        round_of(call("check_rules", **draft)),
        round_of(call("submit_script", **draft, risks=[])),
    ]
    code = main([
        "--input", str(INPUT),
        "--mock-script", str(write_mock(tmp_path, steps)),
        "--fail-tool", "estimate_duration", "--fail-times", "1",
        "--out-dir", str(tmp_path / "out"),
    ])
    assert code == 0
    lines = read_jsonl(tmp_path / "out" / "trace.jsonl")
    assert lines[0]["fault"] == {"tool": "estimate_duration", "times": 1}
    estimates = [x for x in lines if x["type"] == "step" and x["action"] == "estimate_duration"]
    assert estimates[0]["injected_fault"] is True and estimates[0]["result"]["ok"] is False


def test_non_sk_api_key_is_redacted_from_trace(tmp_path, monkeypatch):
    """不是 sk- 形状的密钥也要靠 TraceRecorder(secrets=...) 才挡得住。"""
    key = "plain-custom-key-12345"
    monkeypatch.setenv("LLM_API_KEY", key)
    steps = [round_of(call("search_materials", query="字幕", decision_note=f"用 {key} 调试"))]
    main(["--input", str(INPUT), "--mock-script", str(write_mock(tmp_path, steps)), "--out-dir", str(tmp_path / "out")])
    for path in (tmp_path / "out").iterdir():
        assert key not in path.read_text(encoding="utf-8"), path.name
    assert "***" in (tmp_path / "out" / "trace.jsonl").read_text(encoding="utf-8")


def test_mock_banner_is_first_line_of_script_md(tmp_path):
    main(["--input", str(INPUT), "--mock-script", str(MOCK), "--out-dir", str(tmp_path)])
    first = (tmp_path / "script.md").read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("[MOCK]") or first.startswith("> [MOCK]")
