import pytest
from pydantic import ValidationError

from helpers import fit_draft
from script_agent.models import (
    ScriptDraft,
    draft_hash,
    missing_required,
    normalize_request,
    optional_assumptions,
)


@pytest.mark.parametrize("value,expected", [(30, 30.0), (12.5, 12.5), ("30", 30.0), ("30秒", 30.0), ("30s", 30.0), (" 30 ", 30.0), (600, 600.0)])
def test_valid_target(value, expected):
    assert normalize_request({"target_duration_sec": value}).target_duration_sec == expected

@pytest.mark.parametrize("value", [0, -5, "三十秒", 601, True, "nan", "inf", "abc"])
def test_invalid_target_is_treated_as_missing(value):
    req = normalize_request({"topic": "字幕", "target_duration_sec": value})
    assert req.target_duration_sec is None
    assert "target_duration_sec" in req.invalid_fields
    assert missing_required(req) == ["target_duration_sec"]

def test_absent_target_is_missing_but_not_invalid():
    req = normalize_request({"topic": "字幕"})
    assert req.invalid_fields == {}
    assert missing_required(req) == ["target_duration_sec"]

def test_blank_topic_is_missing():
    assert missing_required(normalize_request({"topic": "   "})) == ["topic", "target_duration_sec"]

def test_optional_assumptions_cover_missing_fields():
    assert len(optional_assumptions(normalize_request({"topic": "字幕", "target_duration_sec": 30}))) == 3
    full = {"topic": "字幕", "target_duration_sec": 30, "audience": "新手", "platform": "抖音", "style": "轻松"}
    assert optional_assumptions(normalize_request(full)) == []

def test_draft_hash_ignores_extra_fields_but_tracks_content():
    raw = fit_draft()
    with_extra = fit_draft()
    with_extra["shots"][0]["duration_sec"] = 1
    assert draft_hash(ScriptDraft.model_validate(raw)) == draft_hash(ScriptDraft.model_validate(with_extra))
    changed = fit_draft()
    changed["shots"][1]["narration"] += "嗯"
    assert draft_hash(ScriptDraft.model_validate(raw)) != draft_hash(ScriptDraft.model_validate(changed))

def test_empty_draft_is_rejected():
    with pytest.raises(ValidationError):
        ScriptDraft.model_validate({"title": "t", "shots": []})
