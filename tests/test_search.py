import pytest
from helpers import DATA_DIR
from script_agent.catalog import load_catalog
from script_agent.tools import search_materials

CATALOG = load_catalog(DATA_DIR)
ids = lambda query, **kw: [m["id"] for m in search_materials(CATALOG, query, **kw)["materials"]]

@pytest.mark.parametrize("query,expected", [
    ("字幕", ["P01"]),
    ("字幕功能介绍", ["P01"]),
    ("字幕 模板", ["P01", "P02"]),
    ("1080p", ["P03"]),
])
def test_search_hits(query, expected):
    assert ids(query) == expected

@pytest.mark.parametrize("query", ["让视频自动出现文字", "直播推流", "剪刀鱼", "视频", "功能", "量子计算"])
def test_search_misses(query):
    result = search_materials(CATALOG, query)
    assert result["ok"] is True and result["count"] == 0 and result["materials"] == []

def test_top_k_limits_results():
    assert ids("字幕 模板 配音", top_k=2) == ["P01", "P02"]

def test_result_contains_exact_facts():
    assert search_materials(CATALOG, "字幕")["materials"][0]["facts"] == ["支持字幕"]

def test_blank_query_raises():
    with pytest.raises(ValueError):
        search_materials(CATALOG, " ， ")
