"""真实运行结果的一致性校验；未生成 examples/real/summary.json 时整体跳过。"""

import json
from pathlib import Path

import pytest

from script_agent.catalog import load_catalog
from script_agent.models import ScriptDraft
from script_agent.tools import check_rules, estimate_duration

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "examples/real"
CASES = json.loads((ROOT / "examples/cases.json").read_text(encoding="utf-8"))
pytestmark = pytest.mark.skipif(not (REAL / "summary.json").exists(), reason="尚未生成真实运行结果")

def load(name):
    result = json.loads((REAL / name / "result.json").read_text(encoding="utf-8"))
    lines = [json.loads(x) for x in (REAL / name / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    return result, lines

def steps_of(lines):
    return [x for x in lines if x["type"] == "step"]

def actions(lines, name):
    return [s for s in steps_of(lines) if s["action"] == name]

@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_status_and_real_mode(case):
    result, lines = load(case["name"])
    assert result["status"] in case["expect"]["status"]
    assert result["mode"] == "real" and lines[0]["mode"] == "real" and lines[0]["model"] != "scripted"
    assert lines[-1]["total_tokens"] > 0
    assert result["steps_used"] <= lines[0]["max_steps"]

@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_trace_steps_are_complete(case):
    _, lines = load(case["name"])
    for s in steps_of(lines):
        assert s["action"] and s["result_summary"] and s["next_action"]
        assert "args" in s
        if s["result"].get("error", {}).get("code") != "INVALID_ARGS":
            assert s["decision_note"]

@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_final_script_has_no_forbidden_text(case):
    result, _ = load(case["name"])
    parts = [result.get("title") or ""]
    for shot in result.get("shots") or []:
        parts += [shot["narration"], shot["visual"]]
    text = " ".join(parts)
    assert not any(word in text for word in case["expect"]["forbid_text"])

@pytest.mark.parametrize("case", [c for c in CASES if "completed" in c["expect"]["status"]], ids=lambda c: c["name"])
def test_completed_results_recompute_exactly(case):
    result, lines = load(case["name"])
    if result["status"] != "completed":
        pytest.skip("该用例本次未走到 completed")
    catalog = load_catalog(ROOT / case["data_dir"])
    draft = ScriptDraft.model_validate({"title": result["title"], "shots": result["shots"]})
    retrieved = {m["id"] for s in actions(lines, "search_materials") if s["result"].get("ok") for m in s["result"]["materials"]}
    estimate = estimate_duration(catalog.duration, draft, result["target_duration_sec"])
    assert estimate["verdict"] == "pass"
    assert estimate["total_duration_sec"] == result["total_duration_sec"]
    assert [s["duration_sec"] for s in estimate["shots"]] == [s["duration_sec"] for s in result["shots"]]
    assert check_rules(catalog, draft, retrieved)["verdict"] == "pass"
    for shot in result["shots"]:
        assert shot["source_ids"] == sorted({c["source_id"] for c in shot["claims"]})
        for claim in shot["claims"]:
            assert claim["quote"] in catalog.material(claim["source_id"]).facts
    assert set(case["expect"].get("must_cite", [])) <= set(result["source_ids"])

def test_02_asks_for_target():
    result, _ = load("02_missing_target")
    assert "target_duration_sec" in result["missing_info"] and result["shots"] is None

def test_03_tries_search_then_asks_for_materials():
    result, lines = load("03_no_material")
    assert "materials" in result["missing_info"]
    assert len(actions(lines, "search_materials")) >= 2
    queries = [s["args"]["query"] for s in actions(lines, "search_materials")]
    assert len(set(queries)) == len(queries)

def test_04_recovers_after_failure():
    result, lines = load("04_tool_fail_transient")
    calls = actions(lines, "estimate_duration")
    assert calls[0]["injected_fault"] is True and calls[0]["result"]["ok"] is False
    assert any(c["result"].get("verdict") == "pass" for c in calls[1:])
    assert result["checks"]["duration"] == "pass"

def test_05_never_claims_rule_pass():
    result, lines = load("05_tool_fail_permanent")
    assert result["checks"]["rules"] == "error" and result["shots"] is None
    assert not any(s["result"].get("verdict") == "pass" for s in actions(lines, "check_rules"))

def test_06_corrects_over_duration():
    result, lines = load("06_over_duration_fixed")
    verdicts = [s["result"]["verdict"] for s in actions(lines, "estimate_duration") if s["result"].get("ok")]
    assert verdicts[0] == "too_long" and verdicts[-1] == "pass"
    assert result["total_duration_sec"] <= 12

def test_07_states_failure_without_inventing_duration():
    result, _ = load("07_over_duration_infeasible")
    assert result["shots"] is None and result["total_duration_sec"] is None
    assert result["target_duration_sec"] == 3.0
    assert result["last_estimate"]["verdict"] == "too_long"

def test_08_handles_unsupported_request_visibly():
    result, _ = load("08_rule_conflict")
    if result["status"] == "completed":
        assert any("80" in risk or "效率" in risk for risk in result["risks"])

def test_10_action_changes_when_materials_change():
    changed, _ = load("10_materials_changed")
    original, _ = load("01_normal")
    assert original["status"] == "completed" and changed["status"] == "needs_input"
    assert "P01" not in changed["source_ids"]

def test_at_least_two_distinct_paths():
    paths = {tuple(s["action"] for s in steps_of(load(c["name"])[1])) for c in CASES}
    assert len(paths) >= 2

def test_rule_correction_path_exists():
    def corrected(name):
        verdicts = [s["result"]["verdict"] for s in actions(load(name)[1], "check_rules") if s["result"].get("ok")]
        return "fail" in verdicts and verdicts[-1] == "pass"
    assert any(corrected(c["name"]) for c in CASES)
