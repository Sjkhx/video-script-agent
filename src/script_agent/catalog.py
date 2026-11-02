from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError


class DataError(Exception):
    """数据文件缺失、JSON 损坏或字段不合法。"""


class Material(BaseModel):
    id: str
    product: str
    topic: str
    tags: list[str]
    facts: list[str]


class BrandRules(BaseModel):
    max_title_chars: int
    closing_slogan: str
    banned_terms: list[str]
    unsupported_unless_in_source: list[str]


class DurationConfig(BaseModel):
    chars_per_sec: float
    pause_per_shot_sec: float
    min_shot_sec: float
    lower_ratio: float


class Catalog(BaseModel):
    materials: list[Material]
    rules: BrandRules
    duration: DurationConfig

    def material(self, source_id: str) -> Material | None:
        for material in self.materials:
            if material.id == source_id:
                return material
        return None


_MATERIALS = TypeAdapter(list[Material])


def _read_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DataError(f"无法读取数据文件：{path}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataError(f"数据文件 JSON 损坏：{path}") from exc


def load_catalog(data_dir: Path) -> Catalog:
    data_dir = Path(data_dir)
    try:
        materials = _MATERIALS.validate_python(_read_json(data_dir / "materials.json"))
        rules = BrandRules.model_validate(_read_json(data_dir / "brand_rules.json"))
        duration = DurationConfig.model_validate(
            _read_json(data_dir / "duration_config.json")
        )
    except ValidationError as exc:
        raise DataError(f"数据字段不合法：{data_dir}") from exc
    return Catalog(materials=materials, rules=rules, duration=duration)
