"""Agent 可调用的工具函数。"""

from __future__ import annotations

import re
import unicodedata

from .catalog import Catalog, Material

_SPLIT_PATTERN = re.compile(r"[\s,，、/;；]+")


def _query_terms(query: str) -> list[str]:
    """NFKC 规范化并转小写，按分隔符切成非空词项。"""
    normalized = unicodedata.normalize("NFKC", query).lower()
    return [term for term in _SPLIT_PATTERN.split(normalized) if term]


def _match_score(material: Material, terms: list[str]) -> int:
    """命中词项数 + 标签作为词项子串且不等于该词项的个数。"""
    text = " ".join([material.topic, *material.tags, *material.facts]).lower()
    score = sum(1 for term in terms if term in text)
    tags = [tag.lower() for tag in material.tags]
    score += sum(
        1 for tag in tags if any(tag != term and tag in term for term in terms)
    )
    return score


def search_materials(catalog: Catalog, query: str, top_k: int = 5) -> dict:
    """检索素材：得分大于 0 的结果按（得分降序，ID 升序）取前 top_k 个。"""
    terms = _query_terms(query)
    if not terms:
        raise ValueError("查询切分后没有词项")
    hits = []
    for material in catalog.materials:
        score = _match_score(material, terms)
        if score > 0:
            hits.append((score, material))
    hits.sort(key=lambda hit: (-hit[0], hit[1].id))
    hits = hits[:top_k]
    return {
        "ok": True,
        "query": query,
        "count": len(hits),
        "materials": [
            {"id": material.id, "topic": material.topic, "facts": list(material.facts)}
            for _, material in hits
        ],
    }
