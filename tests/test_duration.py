import pytest

from helpers import DATA_DIR, SLOGAN, fit_draft
from script_agent.catalog import load_catalog
from script_agent.models import ScriptDraft
from script_agent.tools import count_speech_units, estimate_duration

CONFIG = load_catalog(DATA_DIR).duration


def estimate(draft, target=30):
    return estimate_duration(CONFIG, ScriptDraft.model_validate(draft), target)


@pytest.mark.parametrize("text,units", [
    ("这款产品支持字幕。", 8), ("支持1080P导出", 7), ("Hello world", 6), ("。，！  ", 0), ("８０％", 1), (SLOGAN, 11),
])
def test_count_speech_units(text, units):
    assert count_speech_units(text) == units


@pytest.mark.parametrize("draft,total,verdict,overflow,shortfall", [
    (fit_draft(), 30.0, "pass", 0.0, 0.0),
    (fit_draft(4, 26), 28.0, "pass", 0.0, 0.0),
    (fit_draft(4, 22), 24.0, "pass", 0.0, 0.0),
    (fit_draft(5), 37.5, "too_long", 7.5, 0.0),
    (fit_draft(3, 22), 18.0, "too_short", 0.0, 6.0),
])
def test_verdict_at_target_30(draft, total, verdict, overflow, shortfall):
    r = estimate(draft)
    assert (r["total_duration_sec"], r["verdict"], r["overflow_sec"], r["shortfall_sec"]) == (total, verdict, overflow, shortfall)
    assert (r["min_allowed_sec"], r["max_allowed_sec"]) == (24.0, 30)


def test_shot_durations_sum_to_total_and_min_applies():
    draft = {"title": "t", "shots": [
        {"id": 1, "visual": "v", "narration": "好"},
        {"id": 2, "visual": "v", "narration": "这款产品支持字幕。"},
        {"id": 3, "visual": "v", "narration": "支持1080P导出"},
    ]}
    r = estimate(draft)
    assert [s["duration_sec"] for s in r["shots"]] == [2.0, 2.5, 2.25]
    assert r["total_duration_sec"] == 6.75


def test_three_second_target_is_impossible_with_slogan():
    draft = {"title": "t", "shots": [{"id": 1, "visual": "v", "narration": SLOGAN}]}
    r = estimate(draft, target=3)
    assert (r["total_duration_sec"], r["verdict"], r["overflow_sec"]) == (3.25, "too_long", 0.25)
