"""Skill resolution and composition.

Determines which skills are active for a given session or request,
resolves conflicts, and composes the final skill context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from caw.errors import SkillError

if TYPE_CHECKING:
    from caw.skills.loader import SkillDocument


@dataclass
class ResolvedSkillSet:
    """The result of skill resolution."""

    skills: list[SkillDocument]
    composed_context: str
    conflicts_resolved: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SkillResolver:
    """Resolves which skills are active and composes them."""

    _SPECIFICITY: ClassVar[dict[str, int]] = {"builtin": 0, "mode": 1, "pack": 2, "explicit": 3}

    def __init__(self, available_skills: list[SkillDocument]) -> None:
        """Initialize with the full set of available skills."""
        self._skill_by_id = {skill.skill_id: skill for skill in available_skills}

    def resolve(
        self,
        explicit_ids: list[str] | None = None,
        pack_ids: list[str] | None = None,
        mode_default_ids: list[str] | None = None,
        builtin_ids: list[str] | None = None,
    ) -> ResolvedSkillSet:
        """Resolve the active skill set."""
        warnings: list[str] = []
        conflicts_resolved: list[str] = []

        requested: dict[str, str] = {}
        for source_name, skill_ids in [
            ("builtin", builtin_ids or []),
            ("mode", mode_default_ids or []),
            ("pack", pack_ids or []),
            ("explicit", explicit_ids or []),
        ]:
            for skill_id in skill_ids:
                current = requested.get(skill_id)
                if current is None or self._SPECIFICITY[source_name] > self._SPECIFICITY[current]:
                    requested[skill_id] = source_name

        active: dict[str, tuple[SkillDocument, str]] = {}
        for skill_id, source_name in requested.items():
            skill = self._skill_by_id.get(skill_id)
            if skill is None:
                warnings.append(f"Skill '{skill_id}' not found in available skills")
                continue
            active[skill_id] = (skill, source_name)

        while True:
            conflict = self._find_conflict(active=active)
            if conflict is None:
                break

            left_skill, left_source, right_skill, right_source = conflict
            winner, loser = self._resolve_conflict(
                left_skill=left_skill,
                left_source=left_source,
                right_skill=right_skill,
                right_source=right_source,
            )
            if winner is None or loser is None:
                raise SkillError(
                    message=(
                        f"Unresolvable skill conflict between '{left_skill.skill_id}' and "
                        f"'{right_skill.skill_id}'."
                    ),
                    code="skill_conflict_unresolvable",
                )
            active.pop(loser.skill_id)
            conflicts_resolved.append(
                f"{winner.skill_id} overrides {loser.skill_id} due to precedence rules"
            )

        ordered_skills = sorted(
            active.values(), key=lambda item: (item[0].priority, item[0].skill_id)
        )
        resolved_skills = [item[0] for item in ordered_skills]
        composed = self._compose_context(resolved_skills)
        return ResolvedSkillSet(
            skills=resolved_skills,
            composed_context=composed,
            conflicts_resolved=conflicts_resolved,
            warnings=warnings,
        )

    def _find_conflict(
        self, active: dict[str, tuple[SkillDocument, str]]
    ) -> tuple[SkillDocument, str, SkillDocument, str] | None:
        skill_ids = sorted(active.keys())
        for skill_id in skill_ids:
            skill, source = active[skill_id]
            for conflict_id in skill.conflicts_with:
                if conflict_id in active:
                    conflict_skill, conflict_source = active[conflict_id]
                    return skill, source, conflict_skill, conflict_source
        return None

    def _resolve_conflict(
        self,
        left_skill: SkillDocument,
        left_source: str,
        right_skill: SkillDocument,
        right_source: str,
    ) -> tuple[SkillDocument | None, SkillDocument | None]:
        if left_skill.priority > right_skill.priority:
            return left_skill, right_skill
        if right_skill.priority > left_skill.priority:
            return right_skill, left_skill

        left_specificity = self._SPECIFICITY[left_source]
        right_specificity = self._SPECIFICITY[right_source]
        if left_specificity > right_specificity:
            return left_skill, right_skill
        if right_specificity > left_specificity:
            return right_skill, left_skill

        return None, None

    def _compose_context(self, skills: list[SkillDocument]) -> str:
        parts: list[str] = []
        for skill in skills:
            parts.append(f"<!-- BEGIN SKILL: {skill.skill_id} -->")
            parts.append(skill.body.strip())
            parts.append(f"<!-- END SKILL: {skill.skill_id} -->")
        return "\n\n".join(parts).strip()
