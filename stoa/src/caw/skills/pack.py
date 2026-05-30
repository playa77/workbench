"""Skill pack parsing and loading."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from caw.errors import SkillError


@dataclass
class SkillPackEntry:
    """Entry describing a skill reference inside a skill pack."""

    skill_id: str
    version_constraint: str = ">=0.0.0"
    priority_override: int | None = None


@dataclass
class SkillPack:
    """Parsed skill pack definition."""

    pack_id: str
    version: str
    name: str
    description: str
    skills: list[SkillPackEntry]
    config_overrides: dict[str, object] = field(default_factory=dict)
    source_path: Path | None = None


def load_skill_pack(path: Path) -> SkillPack:
    """Load a skill pack from a TOML file."""
    if not path.exists():
        raise SkillError(
            message=f"Skill pack '{path}' does not exist.", code="skill_pack_not_found"
        )
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SkillError(
            message=f"Failed to parse skill pack '{path}': {exc}",
            code="skill_pack_parse_failed",
        ) from exc

    return _pack_from_mapping(data=raw, path=path)


def _pack_from_mapping(data: dict[str, Any], path: Path) -> SkillPack:
    pack = data.get("pack")
    if not isinstance(pack, dict):
        raise SkillError(
            message=f"Skill pack '{path}' must include a [pack] table.",
            code="skill_pack_missing_pack_table",
        )

    raw_skills = pack.get("skills", [])
    if not isinstance(raw_skills, list):
        raise SkillError(
            message=f"Skill pack '{path}' [pack.skills] must be an array.",
            code="skill_pack_invalid_skills",
        )

    skills: list[SkillPackEntry] = []
    for item in raw_skills:
        if not isinstance(item, dict) or "skill_id" not in item:
            raise SkillError(
                message=f"Skill pack '{path}' contains an invalid skill entry.",
                code="skill_pack_invalid_skill_entry",
            )
        skills.append(
            SkillPackEntry(
                skill_id=str(item["skill_id"]),
                version_constraint=str(item.get("version", ">=0.0.0")),
                priority_override=(
                    int(item["priority_override"])
                    if item.get("priority_override") is not None
                    else None
                ),
            )
        )

    config_overrides_raw = pack.get("config_overrides", {})
    config_overrides: dict[str, object] = {}
    if isinstance(config_overrides_raw, dict):
        config_overrides = dict(config_overrides_raw)

    return SkillPack(
        pack_id=str(pack.get("pack_id", "")),
        version=str(pack.get("version", "")),
        name=str(pack.get("name", "")),
        description=str(pack.get("description", "")),
        skills=skills,
        config_overrides=config_overrides,
        source_path=path,
    )


def load_all_packs(directory: Path) -> list[SkillPack]:
    """Load all skill packs from a directory."""
    if not directory.exists() or not directory.is_dir():
        return []

    packs: list[SkillPack] = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix == ".toml":
            packs.append(load_skill_pack(path))
    return packs
