"""Agent 可调用的工具函数。"""

from __future__ import annotations

import math
import re
import unicodedata

from .catalog import Catalog, DurationConfig, Material
from .models import ScriptDraft

_SPLIT_PATTERN = re.compile(r"[\s,，、/;；]+")
_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_ALNUM_PATTERN = re.compile(r"[A-Za-z0-9]+")


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


def count_speech_units(text: str) -> int:
    """NFKC 后统计计时单位：每个汉字计 1，每段连续字母数字计 ceil(长度 / 2)。"""
    normalized = unicodedata.normalize("NFKC", text)
    units = len(_CJK_PATTERN.findall(normalized))
    units += sum(math.ceil(len(run) / 2) for run in _ALNUM_PATTERN.findall(normalized))
    return units


def estimate_duration(
    config: DurationConfig, draft: ScriptDraft, target_sec: float
) -> dict:
    """按配置估算分镜时长并给出时长判定，总时长取各分镜已舍入值之和。"""
    shots = []
    for shot in draft.shots:
        units = count_speech_units(shot.narration)
        duration_sec = round(
            max(
                config.min_shot_sec,
                units / config.chars_per_sec + config.pause_per_shot_sec,
            ),
            2,
        )
        shots.append({"id": shot.id, "units": units, "duration_sec": duration_sec})
    total = round(sum(shot["duration_sec"] for shot in shots), 2)
    min_allowed = round(target_sec * config.lower_ratio, 2)
    if total > target_sec:
        verdict = "too_long"
    elif total < min_allowed:
        verdict = "too_short"
    else:
        verdict = "pass"
    return {
        "ok": True,
        "shots": shots,
        "total_duration_sec": total,
        "target_duration_sec": target_sec,
        "min_allowed_sec": min_allowed,
        "max_allowed_sec": target_sec,
        "verdict": verdict,
        "overflow_sec": round(max(0.0, total - target_sec), 2),
        "shortfall_sec": round(max(0.0, min_allowed - total), 2),
    }
