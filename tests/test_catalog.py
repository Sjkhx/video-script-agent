import shutil
from pathlib import Path

import pytest

from script_agent.catalog import DataError, load_catalog

DATA = Path(__file__).resolve().parents[1] / "data"


def test_load_catalog_has_reference_material():
    c = load_catalog(DATA)
    assert c.material("P01").facts == ["支持字幕"]
    assert c.material("P99") is None
    assert c.duration.chars_per_sec == 4.0
    assert c.rules.closing_slogan == "剪刀鱼，剪出属于你的故事"


def test_searchable_text_excludes_generic_words():
    for m in load_catalog(DATA).materials:
        text = " ".join([m.topic, *m.tags, *m.facts])
        assert not any(word in text for word in ["剪刀鱼", "视频", "功能"])


def test_missing_dir_raises_data_error(tmp_path):
    with pytest.raises(DataError):
        load_catalog(tmp_path / "nope")


def test_corrupt_json_raises_data_error(tmp_path):
    for name in ["materials.json", "brand_rules.json", "duration_config.json"]:
        shutil.copy(DATA / name, tmp_path / name)
    (tmp_path / "materials.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(DataError):
        load_catalog(tmp_path)


def test_variant_has_no_p01():
    variant = DATA.parent / "examples" / "data_variants" / "no_subtitle"
    assert load_catalog(variant).material("P01") is None
