"""Skill registry for loaded skill documents and packs."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from caw.models import SessionMode
from caw.skills.loader import SkillDocument, load_all_skills
from caw.skills.pack import SkillPack, load_all_packs
from caw.skills.resolver import SkillResolver

if TYPE_CHECKING:
    from caw.core.config import SkillsConfig


class SkillRegistry:
    """Central registry for skills and skill packs."""

    _MODE_DEFAULTS: ClassVar[dict[SessionMode, list[str]]] = {
        SessionMode.CHAT: [],
        SessionMode.RESEARCH: ["caw.builtin.research_operator"],
        SessionMode.DELIBERATION: ["caw.builtin.deliberation_director"],
        SessionMode.WORKSPACE: ["caw.builtin.workspace_operator"],
        SessionMode.ARENA: [],
    }

    def __init__(self, config: SkillsConfig) -> None:
        self._config = config
        self._skills: dict[str, SkillDocument] = {}
        self._packs: dict[str, SkillPack] = {}

    def load(self) -> None:
        """Load all skills and packs from configured directories."""
        self._skills.clear()
        self._packs.clear()

        builtin_dir = Path(self._config.builtin_dir).expanduser()
        user_dir = Path(self._config.user_dir).expanduser()
        packs_dir = Path(self._config.packs_dir).expanduser()

        for skill in load_all_skills(builtin_dir) + load_all_skills(user_dir):
            self._skills[skill.skill_id] = skill

        for pack in load_all_packs(packs_dir):
            self._packs[pack.pack_id] = pack

    def get_skill(self, skill_id: str) -> SkillDocument | None:
        return self._skills.get(skill_id)

    def get_pack(self, pack_id: str) -> SkillPack | None:
        return self._packs.get(pack_id)

    def list_skills(self) -> list[SkillDocument]:
        return sorted(self._skills.values(), key=lambda skill: skill.skill_id)

    def list_packs(self) -> list[SkillPack]:
        return sorted(self._packs.values(), key=lambda pack: pack.pack_id)

    def get_mode_defaults(self, mode: SessionMode) -> list[str]:
        return list(self._MODE_DEFAULTS.get(mode, []))

    def create_resolver(self) -> SkillResolver:
        """Create a SkillResolver with all loaded skills."""
        return SkillResolver(available_skills=self.list_skills())
