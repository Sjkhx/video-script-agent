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
_NUMBER_PATTERN = re.compile(
    r"\d+(?:\.\d+)?%?"
    r"|百分之[一二三四五六七八九十百]+"
    r"|[一二三四五六七八九十两]+(?:倍|成|折)"
)
_SLOGAN_TRIM_PATTERN = re.compile(r"[\s。.!?~]+$")
_PART_LABELS = {"title": "标题", "narration": "旁白", "visual": "画面"}


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


def _fold(text: str) -> str:
    """NFKC 规范化并转小写，规则检查的所有文本比较都先经过它。"""
    return unicodedata.normalize("NFKC", text).lower()


def _contains_folded(folded_text: str, term: str) -> bool:
    """在已折叠文本中按忽略大小写的子串查找非空词项。"""
    folded_term = _fold(term)
    return bool(folded_term) and folded_term in folded_text


def _contains_term(folded_text: str, term: str) -> bool:
    """查找词项：纯英文词按字母边界匹配，其余按忽略大小写的子串匹配。"""
    folded_term = _fold(term)
    if not folded_term:
        return False
    if folded_term.isascii() and folded_term.isalpha():
        pattern = rf"(?<![A-Za-z]){re.escape(folded_term)}(?![A-Za-z])"
        return re.search(pattern, folded_text) is not None
    return folded_term in folded_text


def _contains_number(folded_fact: str, number: str) -> bool:
    """数字须作为完整数字出现，不能是更长数字串的片段。"""
    pattern = rf"(?<!\d){re.escape(number)}(?!\d)"
    return re.search(pattern, folded_fact) is not None


def _text_violations(
    catalog: Catalog,
    text: str,
    part: str,
    shot_id: int | None,
    cited_ids: set[str],
) -> list[dict]:
    """检查一段文本的禁用词、未支持词/数字与未引用标签。"""
    rules = catalog.rules
    label = _PART_LABELS[part]
    folded = _fold(text)
    folded_facts: list[str] = []
    for source_id in sorted(cited_ids):
        material = catalog.material(source_id)
        if material is not None:
            folded_facts.extend(_fold(fact) for fact in material.facts)

    violations: list[dict] = []
    for term in dict.fromkeys(rules.banned_terms):
        if _contains_folded(folded, term):
            violations.append(
                {
                    "code": "BANNED_TERM",
                    "shot_id": shot_id,
                    "detail": f"{label}含品牌禁用词「{term}」，请删除或替换。",
                    "evidence": term,
                }
            )

    for term in dict.fromkeys(rules.unsupported_unless_in_source):
        if not _contains_term(folded, term):
            continue
        if any(_contains_term(fact, term) for fact in folded_facts):
            continue
        violations.append(
            {
                "code": "UNSUPPORTED_TERM",
                "shot_id": shot_id,
                "detail": f"{label}含「{term}」，素材未支持，请删除或引用支持它的素材。",
                "evidence": term,
            }
        )

    for number in dict.fromkeys(_NUMBER_PATTERN.findall(folded)):
        if any(_contains_number(fact, number) for fact in folded_facts):
            continue
        violations.append(
            {
                "code": "UNSUPPORTED_NUMBER",
                "shot_id": shot_id,
                "detail": f"{label}含数字「{number}」，素材未支持，请删除或引用支持它的素材。",
                "evidence": number,
            }
        )

    for material in catalog.materials:
        if material.id in cited_ids:
            continue
        for tag in dict.fromkeys(material.tags):
            if _contains_folded(folded, tag):
                violations.append(
                    {
                        "code": "UNCITED_FEATURE",
                        "shot_id": shot_id,
                        "detail": (
                            f"{label}提到素材 {material.id} 的标签「{tag}」，"
                            f"但未引用该素材；请补充引用 {material.id} 或删除该说法。"
                        ),
                        "evidence": f"{material.id}:{tag}",
                    }
                )
    return violations


def _ends_with_slogan(narration: str, slogan: str) -> bool:
    """去掉末尾的 。.!?~ 和空格后，判断旁白是否以品牌语结尾。"""
    normalized = unicodedata.normalize("NFKC", narration)
    expected = unicodedata.normalize("NFKC", slogan)
    return _SLOGAN_TRIM_PATTERN.sub("", normalized).endswith(
        _SLOGAN_TRIM_PATTERN.sub("", expected)
    )


def check_rules(
    catalog: Catalog, draft: ScriptDraft, retrieved_ids: set[str]
) -> dict:
    """检查品牌规则与素材来源；verdict 为 pass 当且仅当违规列表为空。"""
    rules = catalog.rules
    violations: list[dict] = []

    def add(code: str, shot_id: int | None, detail: str, evidence: str) -> None:
        violations.append(
            {"code": code, "shot_id": shot_id, "detail": detail, "evidence": evidence}
        )

    if not any(shot.claims for shot in draft.shots):
        add(
            "NO_SOURCE",
            None,
            "全脚本没有任何素材引用，请至少为一个分镜补充 claims。",
            "claims: 0",
        )

    normalized_title = unicodedata.normalize("NFKC", draft.title)
    if len(normalized_title) > rules.max_title_chars:
        add(
            "TITLE_TOO_LONG",
            None,
            f"标题长度 {len(normalized_title)} 字，超过上限 {rules.max_title_chars} 字，请缩短标题。",
            draft.title,
        )

    if not draft.title.strip():
        add("EMPTY_TEXT", None, "标题不能为空，请写一个标题。", draft.title)

    all_cited = {claim.source_id for shot in draft.shots for claim in shot.claims}
    violations.extend(_text_violations(catalog, draft.title, "title", None, all_cited))

    seen_ids: set[int] = set()
    for shot in draft.shots:
        if shot.id <= 0:
            add(
                "INVALID_SHOT_ID",
                shot.id,
                f"分镜序号 {shot.id} 不合法，请使用从 1 开始的正整数。",
                str(shot.id),
            )
        if shot.id in seen_ids:
            add(
                "DUPLICATE_SHOT_ID",
                shot.id,
                f"分镜序号 {shot.id} 重复，请给每个分镜不同的序号。",
                str(shot.id),
            )
        seen_ids.add(shot.id)
        for part in ("visual", "narration"):
            if not getattr(shot, part).strip():
                add(
                    "EMPTY_TEXT",
                    shot.id,
                    f"{_PART_LABELS[part]}不能为空，请补充内容或删除这个分镜。",
                    getattr(shot, part),
                )
        # 纯标点也能拿到单镜最短时长，不拦住就可以用空分镜凑时长。
        if shot.narration.strip() and count_speech_units(shot.narration) == 0:
            add(
                "NO_SPEECH",
                shot.id,
                "旁白只有标点或符号，没有可读出的文字，请写成完整的句子或删除这个分镜。",
                shot.narration,
            )

        cited = {claim.source_id for claim in shot.claims}
        for claim in shot.claims:
            material = catalog.material(claim.source_id)
            if material is None:
                add(
                    "SOURCE_NOT_FOUND",
                    shot.id,
                    f"素材 {claim.source_id} 不在素材库中，请删除该引用或改用库内素材。",
                    claim.source_id,
                )
                continue
            if claim.source_id not in retrieved_ids:
                add(
                    "SOURCE_NOT_RETRIEVED",
                    shot.id,
                    f"素材 {claim.source_id} 未在本次检索结果中，请先检索该素材或删除该引用。",
                    claim.source_id,
                )
            quote = unicodedata.normalize("NFKC", claim.quote)
            facts = {unicodedata.normalize("NFKC", fact) for fact in material.facts}
            if quote not in facts:
                add(
                    "CLAIM_NOT_IN_SOURCE",
                    shot.id,
                    f"引用内容「{claim.quote}」不是素材 {claim.source_id} 的逐字原文，请从素材 facts 中原样引用。",
                    f"{claim.source_id}: {claim.quote}",
                )
        violations.extend(
            _text_violations(catalog, shot.narration, "narration", shot.id, cited)
        )
        violations.extend(
            _text_violations(catalog, shot.visual, "visual", shot.id, cited)
        )

    last_shot = draft.shots[-1]
    if not _ends_with_slogan(last_shot.narration, rules.closing_slogan):
        add(
            "MISSING_CLOSING_SLOGAN",
            last_shot.id,
            f"最后一个分镜旁白必须以品牌语「{rules.closing_slogan}」结尾"
            "（比较时忽略末尾的 。.!?~ 和空格）。",
            last_shot.narration,
        )

    unique: list[dict] = []
    seen: set[tuple[str, int | None, str]] = set()
    for violation in violations:
        key = (
            violation["code"],
            violation["shot_id"],
            violation["detail"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(violation)
    return {
        "ok": True,
        "verdict": "pass" if not unique else "fail",
        "violations": unique,
    }
