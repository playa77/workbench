from pathlib import Path

import pytest

from caw.errors import SkillError
from caw.skills.loader import discover_skills, load_all_skills, load_skill

FIXTURES = Path("tests/fixtures/skills")


def test_load_valid_basic() -> None:
    skill = load_skill(FIXTURES / "valid_basic.md")
    assert skill.skill_id == "test.basic"
    assert skill.version == "1.0.0"
    assert skill.priority == 100
    assert skill.body


def test_load_valid_full() -> None:
    skill = load_skill(FIXTURES / "valid_full.md")
    assert skill.skill_id == "caw.builtin.test_full"
    assert skill.requires_tools == ["retrieval", "file_read"]
    assert skill.requires_permissions == ["read", "write"]
    assert skill.priority == 250
    assert skill.min_context_window == 32000


def test_load_nonexistent_file() -> None:
    with pytest.raises(SkillError):
        load_skill(FIXTURES / "missing.md")


def test_load_no_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "no_frontmatter.md"
    path.write_text("# no frontmatter", encoding="utf-8")
    with pytest.raises(SkillError):
        load_skill(path)


def test_discover_finds_md_files(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("", encoding="utf-8")
    (tmp_path / "b.md").write_text("", encoding="utf-8")
    (tmp_path / "note.txt").write_text("", encoding="utf-8")
    found = discover_skills(tmp_path)
    assert [path.name for path in found] == ["a.md", "b.md"]


def test_load_all_skips_invalid(tmp_path: Path) -> None:
    (tmp_path / "valid.md").write_text((FIXTURES / "valid_basic.md").read_text(encoding="utf-8"))
    (tmp_path / "invalid.md").write_text(
        (FIXTURES / "invalid_missing_id.md").read_text(encoding="utf-8")
    )

    loaded = load_all_skills(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].skill_id == "test.basic"
