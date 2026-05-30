"""Skill document validation.

Validates SkillDocument objects against the schema
defined in Technical Specification §7.1.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from caw.models import PermissionLevel

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|[0-9A-Za-z-]+)(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]+))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
# Claude Skills format: dot-separated lowercase segments;
# each segment may include underscores after the first character.
SKILL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*(?:\.[a-z0-9][a-z0-9_]*)+$")


@dataclass
class ValidationResult:
    """Validation result for a single skill document."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_valid_semver(version: str) -> bool:
    return bool(SEMVER_RE.fullmatch(version))


def validate_skill(skill: object) -> ValidationResult:
    """Validate a loaded skill document.

    Checks:
    1. skill_id is non-empty and matches pattern: lowercase dot-separated segments,
       with optional underscores inside segments.
    2. version is valid SemVer (MAJOR.MINOR.PATCH, optional pre-release).
    3. name is non-empty.
    4. description is non-empty.
    5. author is non-empty.
    6. priority is a positive integer.
    7. requires_permissions values are valid PermissionLevel enum values.
    8. body is non-empty (at least 10 characters of non-whitespace content).
    9. version pre-release identifiers, if present, match SemVer spec.

    Returns:
        ValidationResult with errors and warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []

    skill_id = str(getattr(skill, "skill_id", "")).strip()
    version = str(getattr(skill, "version", "")).strip()
    name = str(getattr(skill, "name", "")).strip()
    description = str(getattr(skill, "description", "")).strip()
    author = str(getattr(skill, "author", "")).strip()
    priority = getattr(skill, "priority", None)
    permissions = getattr(skill, "requires_permissions", [])
    body = str(getattr(skill, "body", ""))

    if not skill_id:
        errors.append("skill_id is required")
    elif not SKILL_ID_RE.fullmatch(skill_id):
        errors.append(
            "skill_id must be lowercase dot-separated segments; underscores are allowed"
        )

    if not version:
        errors.append("version is required")
    elif not _is_valid_semver(version):
        errors.append(f"version '{version}' is not a valid SemVer string")

    if not name:
        errors.append("name is required")
    if not description:
        errors.append("description is required")
    if not author:
        errors.append("author is required")

    if not isinstance(priority, int) or priority <= 0:
        errors.append("priority must be a positive integer")

    valid_permissions = {permission.value for permission in PermissionLevel}
    if not isinstance(permissions, list):
        errors.append("requires_permissions must be a list")
    else:
        invalid_permissions = [item for item in permissions if item not in valid_permissions]
        if invalid_permissions:
            errors.append(
                "requires_permissions contains invalid values: " + ", ".join(invalid_permissions)
            )

    if len(body.strip()) < 10:
        errors.append("body must contain at least 10 non-whitespace characters")

    if skill_id and ".builtin." not in skill_id:
        warnings.append("skill_id does not use the recommended builtin namespace")

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)
