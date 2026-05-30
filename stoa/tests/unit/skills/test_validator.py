from pathlib import Path

from caw.skills.loader import load_skill
from caw.skills.validator import validate_skill

FIXTURES = Path("tests/fixtures/skills")


def test_validate_valid() -> None:
    result = validate_skill(load_skill(FIXTURES / "valid_basic.md"))
    assert result.valid is True
    assert result.errors == []


def test_validate_valid_with_underscore_skill_id() -> None:
    result = validate_skill(load_skill(FIXTURES / "valid_full.md"))
    assert result.valid is True
    assert result.errors == []


def test_validate_missing_id() -> None:
    result = validate_skill(load_skill(FIXTURES / "invalid_missing_id.md"))
    assert result.valid is False
    assert any("skill_id" in error for error in result.errors)


def test_validate_bad_version() -> None:
    result = validate_skill(load_skill(FIXTURES / "invalid_bad_version.md"))
    assert result.valid is False
    assert any("SemVer" in error for error in result.errors)


def test_validate_empty_body() -> None:
    result = validate_skill(load_skill(FIXTURES / "invalid_empty_body.md"))
    assert result.valid is False
    assert any("at least 10" in error for error in result.errors)
