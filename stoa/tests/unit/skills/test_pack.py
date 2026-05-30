from pathlib import Path

import pytest

from caw.errors import SkillError
from caw.skills.pack import load_all_packs, load_skill_pack

FIXTURES = Path("tests/fixtures/skills/packs")


def test_load_valid_pack() -> None:
    pack = load_skill_pack(FIXTURES / "valid_pack.toml")
    assert pack.pack_id == "caw.packs.deep_research"
    assert pack.version == "1.0.0"
    assert len(pack.skills) == 2


def test_load_pack_with_overrides() -> None:
    pack = load_skill_pack(FIXTURES / "valid_pack.toml")
    assert pack.skills[1].priority_override == 150
    assert pack.config_overrides["providers"] == {"default": "anthropic"}


def test_load_invalid_pack() -> None:
    with pytest.raises(SkillError):
        load_skill_pack(FIXTURES / "invalid_pack.toml")


def test_load_all_packs(tmp_path: Path) -> None:
    first = tmp_path / "one.toml"
    second = tmp_path / "two.toml"
    content = (FIXTURES / "valid_pack.toml").read_text(encoding="utf-8")
    first.write_text(content, encoding="utf-8")
    second.write_text(content.replace("deep_research", "deep_research_2"), encoding="utf-8")

    packs = load_all_packs(tmp_path)
    assert len(packs) == 2
