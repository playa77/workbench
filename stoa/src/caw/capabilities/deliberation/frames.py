"""Frame configuration and skill resolution for deliberation flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from caw.errors import ValidationError_

if TYPE_CHECKING:
    from caw.skills.loader import SkillDocument
    from caw.skills.registry import SkillRegistry


@dataclass(slots=True)
class FrameConfig:
    """Configuration for a single deliberation frame/perspective."""

    frame_id: str
    skill_id: str
    label: str
    provider: str | None = None
    model: str | None = None
    initial_context: str | None = None

    def resolve_skill(self, registry: SkillRegistry) -> SkillDocument:
        """Resolve this frame's configured skill from a registry.

        Raises:
            ValidationError_: If the skill ID does not exist.
        """
        skill = registry.get_skill(self.skill_id)
        if skill is None:
            raise ValidationError_(
                message=(
                    f"Invalid frame skill_id '{self.skill_id}' for frame '{self.frame_id}'. "
                    "Ensure the skill exists and is loaded."
                ),
                code="deliberation_invalid_skill",
                details={"frame_id": self.frame_id, "skill_id": self.skill_id},
            )
        return skill
