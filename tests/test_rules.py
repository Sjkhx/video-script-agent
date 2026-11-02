import pytest

from helpers import CLAIM_P01, DATA_DIR, SLOGAN, fit_draft, with_narration
from script_agent.catalog import load_catalog
from script_agent.models import ScriptDraft
from script_agent.tools import check_rules

CATALOG = load_catalog(DATA_DIR)

def codes(draft, retrieved=frozenset({"P01"}), catalog=CATALOG):
    return {v["code"] for v in check_rules(catalog, ScriptDraft.model_validate(draft), set(retrieved))["violations"]}

def test_fit_draft_passes():
    r = check_rules(CATALOG, ScriptDraft.model_validate(fit_draft()), {"P01"})
    assert r["ok"] is True and r["verdict"] == "pass" and r["violations"] == []

def test_source_rules():
    assert "SOURCE_NOT_RETRIEVED" in codes(fit_draft(), frozenset())
    unknown = fit_draft()
    unknown["shots"][0]["claims"] = [{"source_id": "P99", "quote": "x"}]
    assert "SOURCE_NOT_FOUND" in codes(unknown, {"P99"})
    misquote = fit_draft()
    misquote["shots"][0]["claims"] = [{"source_id": "P01", "quote": "支持多语言字幕"}]
    assert "CLAIM_NOT_IN_SOURCE" in codes(misquote)
    no_claims = fit_draft()
    no_claims["shots"][0].update(claims=[], narration="嗯" * 28)
    assert "NO_SOURCE" in codes(no_claims)

def test_reference_case_rejects_invented_effect():
    assert {"UNSUPPORTED_NUMBER", "UNSUPPORTED_TERM"} <= codes(with_narration(1, "效率提升80%"))

@pytest.mark.parametrize("text", ["提高８０％", "快了三倍", "百分之八十的人"])
def test_number_variants_are_rejected(text):
    assert "UNSUPPORTED_NUMBER" in codes(with_narration(1, text))

def test_cited_number_passes():
    claim = [{"source_id": "P03", "quote": "支持导出 1080P"}]
    assert codes(with_narration(1, "支持导出 1080P", claim), {"P01", "P03"}) == set()

def test_uncited_feature_is_rejected():
    assert {"UNCITED_FEATURE", "UNSUPPORTED_NUMBER"} <= codes(with_narration(1, "支持导出 1080P"))
    assert "UNCITED_FEATURE" in codes(with_narration(1, "字幕很重要"))

def test_invented_capability_is_rejected_even_when_cited():
    assert "UNSUPPORTED_TERM" in codes(with_narration(0, "一键加字幕", [dict(CLAIM_P01)]))

def test_title_rules():
    assert "UNSUPPORTED_TERM" in codes(fit_draft(title="一键加字幕，剪辑更省事"))
    assert codes(fit_draft(title="字幕怎么加")) == set()
    assert "TITLE_TOO_LONG" not in codes(fit_draft(title="标" * 20))
    assert "TITLE_TOO_LONG" in codes(fit_draft(title="标" * 21))

def test_term_is_allowed_when_source_supports_it():
    catalog = CATALOG.model_copy(deep=True)
    catalog.material("P01").facts = ["支持多语言字幕"]
    claim = [{"source_id": "P01", "quote": "支持多语言字幕"}]
    assert "UNSUPPORTED_TERM" not in codes(with_narration(0, "支持多语言字幕", claim), catalog=catalog)

def test_banned_term():
    assert "BANNED_TERM" in codes(with_narration(1, "全网第一"))

def test_ascii_term_uses_word_boundary():
    assert "UNSUPPORTED_TERM" in codes(with_narration(1, "用AI写"))
    assert "UNSUPPORTED_TERM" not in codes(with_narration(1, "发Email"))

def test_closing_slogan():
    missing = fit_draft()
    missing["shots"][-1]["narration"] = "嗯" * 28
    r = check_rules(CATALOG, ScriptDraft.model_validate(missing), {"P01"})
    violation = next(v for v in r["violations"] if v["code"] == "MISSING_CLOSING_SLOGAN")
    assert SLOGAN in violation["detail"]
    with_period = fit_draft()
    with_period["shots"][-1]["narration"] += "。"
    assert codes(with_period) == set()
