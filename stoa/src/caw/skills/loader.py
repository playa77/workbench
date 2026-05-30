"""Skill document loader.

Loads skill documents from disk, parses YAML frontmatter
and Markdown body, and returns structured SkillDocument objects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import yaml

from caw.errors import SkillError
from caw.skills.validator import validate_skill

LOGGER = logging.getLogger(__name__)


@dataclass
class SkillDocument:
    """Parsed skill document.

    Attributes:
        skill_id: Dot-namespaced unique identifier (lowercase segments; underscores allowed).
        version: SemVer version string.
        name: Human-readable name.
        description: Purpose summary.
        author: Creator identifier.
        tags: Searchable tags.
        requires_tools: Tool names this skill needs.
        requires_permissions: Minimum permission levels.
        conflicts_with: Skill IDs that cannot coexist.
        priority: Resolution precedence (higher = loaded later).
        provider_preference: Preferred model provider key.
        min_context_window: Minimum context window in tokens.
        body: Markdown body content (everything after frontmatter).
        source_path: File path the skill was loaded from.
    """

    skill_id: str
    version: str
    name: str
    description: str
    author: str
    tags: list[str] = field(default_factory=list)
    requires_tools: list[str] = field(default_factory=list)
    requires_permissions: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)
    priority: int = 100
    provider_preference: str | None = None
    min_context_window: int | None = None
    body: str = ""
    source_path: Path | None = None


def _parse_frontmatter(raw_text: str, path: Path) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter and return frontmatter dict + markdown body."""
    if not raw_text.startswith("---"):
        raise SkillError(
            message=f"Skill file '{path}' is missing YAML frontmatter.",
            code="missing_frontmatter",
        )

    delimiters = [
        index for index, line in enumerate(raw_text.splitlines()) if line.strip() == "---"
    ]
    if len(delimiters) < 2:
        raise SkillError(
            message=f"Skill file '{path}' has malformed YAML frontmatter delimiters.",
            code="malformed_frontmatter",
        )

    lines = raw_text.splitlines()
    frontmatter = "\n".join(lines[1 : delimiters[1]])
    body = "\n".join(lines[delimiters[1] + 1 :]).strip()

    try:
        parsed = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError as exc:
        raise SkillError(
            message=f"Failed to parse YAML frontmatter in '{path}': {exc}",
            code="invalid_frontmatter_yaml",
        ) from exc

    if not isinstance(parsed, dict):
        raise SkillError(
            message=f"Skill frontmatter in '{path}' must be a YAML mapping.",
            code="invalid_frontmatter_type",
        )

    return parsed, body


def _from_mapping(frontmatter: dict[str, Any], body: str, path: Path) -> SkillDocument:
    """Create a SkillDocument from parsed frontmatter and body content."""
    return SkillDocument(
        skill_id=str(frontmatter.get("skill_id", "")),
        version=str(frontmatter.get("version", "")),
        name=str(frontmatter.get("name", "")),
        description=str(frontmatter.get("description", "")),
        author=str(frontmatter.get("author", "")),
        tags=[str(item) for item in frontmatter.get("tags", [])],
        requires_tools=[str(item) for item in frontmatter.get("requires_tools", [])],
        requires_permissions=[str(item) for item in frontmatter.get("requires_permissions", [])],
        conflicts_with=[str(item) for item in frontmatter.get("conflicts_with", [])],
        priority=int(frontmatter.get("priority", 100)),
        provider_preference=(
            str(frontmatter.get("provider_preference"))
            if frontmatter.get("provider_preference") is not None
            else None
        ),
        min_context_window=(
            int(frontmatter.get("min_context_window"))
            if frontmatter.get("min_context_window") is not None
            else None
        ),
        body=body,
        source_path=path,
    )


def load_skill(path: Path) -> SkillDocument:
    """Load a single skill document from a Markdown file.

    Parses YAML frontmatter (between --- delimiters) and
    extracts the Markdown body (everything after the closing ---).

    Args:
        path: Path to the .md skill document.

    Returns:
        Parsed SkillDocument.

    Raises:
        SkillError: If file cannot be read or frontmatter cannot be parsed.
    """
    if not path.exists():
        raise SkillError(
            message=f"Skill file '{path}' does not exist.",
            code="skill_file_not_found",
        )

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillError(
            message=f"Failed to read skill file '{path}': {exc}",
            code="skill_file_read_failed",
        ) from exc

    frontmatter, body = _parse_frontmatter(raw_text=raw_text, path=path)
    return _from_mapping(frontmatter=frontmatter, body=body, path=path)


def discover_skills(directory: Path) -> list[Path]:
    """Discover all .md files in a directory (non-recursive).

    Returns:
        Sorted list of .md file paths.
    """
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir() if path.is_file() and path.suffix == ".md")


def load_all_skills(directory: Path) -> list[SkillDocument]:
    """Load all skill documents from a directory.

    Loads each .md file, skipping files that fail validation
    (logged as warnings, not fatal).

    Returns:
        List of successfully loaded SkillDocuments.
    """
    loaded: list[SkillDocument] = []
    for skill_path in discover_skills(directory=directory):
        try:
            skill = load_skill(skill_path)
            validation = validate_skill(skill)
            if not validation.valid:
                LOGGER.warning(
                    "Skill validation failed for '%s': %s",
                    skill_path,
                    "; ".join(validation.errors),
                )
                continue
            loaded.append(skill)
        except (SkillError, ValueError) as exc:
            LOGGER.warning("Skipping skill '%s': %s", skill_path, exc)
    return loaded
