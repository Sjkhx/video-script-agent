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

# 前三批真实运行或探测里出现过的说法：素材 P01 只写了“支持字幕”，这些都超出了原文。
@pytest.mark.parametrize("text", [
    "字幕放哪都行，别挡住画面重点。",
    "加字幕它能帮你搞定。",
    "字幕跟着人声逐句出现。",
    "这款产品的字幕能自己生成。",
    "说一句话就能变成字幕，再也不用手打。",
    "比其他软件好用得多，字幕更准。",
    "这一步不用你一个人硬扛。",
])
def test_invented_capability_in_narration_is_rejected(text):
    assert "UNSUPPORTED_TERM" in codes(with_narration(0, text, [dict(CLAIM_P01)]))

def test_invented_capability_in_visual_is_rejected():
    draft = fit_draft()
    draft["shots"][0]["visual"] = "文字跟着人声逐句出现"
    assert "UNSUPPORTED_TERM" in codes(draft)

def test_invented_effect_in_title_is_rejected():
    assert "UNSUPPORTED_TERM" in codes(fit_draft(title="新手也能顺手出片"))

def test_scene_description_still_passes():
    assert codes(with_narration(1, "刷视频时，你是不是经常静音？")) == set()

@pytest.mark.parametrize("field", ["title", "visual", "narration"])
def test_blank_text_is_rejected(field):
    draft = fit_draft()
    if field == "title":
        draft["title"] = "   "
    else:
        draft["shots"][1][field] = "   "
    assert "EMPTY_TEXT" in codes(draft)

def test_punctuation_only_narration_cannot_pad_duration():
    assert "NO_SPEECH" in codes(with_narration(1, "。。。"))

def test_duplicate_shot_ids_are_rejected():
    draft = fit_draft()
    draft["shots"][1]["id"] = draft["shots"][0]["id"]
    assert "DUPLICATE_SHOT_ID" in codes(draft)

@pytest.mark.parametrize("text", ["提高８０％", "快了三倍", "百分之八十的人"])
def test_number_variants_are_rejected(text):
    assert "UNSUPPORTED_NUMBER" in codes(with_narration(1, text))

def test_cited_number_passes():
    claim = [{"source_id": "P03", "quote": "支持导出 1080P"}]
    assert codes(with_narration(1, "支持导出 1080P", claim), {"P01", "P03"}) == set()

def test_shortened_quantity_is_rejected():
    claim = [{"source_id": "P04", "quote": "提供 12 种中文配音音色"}]
    assert "UNSUPPORTED_NUMBER" in codes(with_narration(1, "提供 1 种音色", claim), {"P01", "P04"})
    claim = [{"source_id": "P03", "quote": "支持导出 1080P"}]
    assert "UNSUPPORTED_NUMBER" in codes(with_narration(1, "支持导出 80P", claim), {"P01", "P03"})

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
