from pathlib import Path

from caw.core.config import SkillsConfig
from caw.skills.loader import load_all_skills
from caw.skills.pack import load_all_packs
from caw.skills.registry import SkillRegistry
from caw.skills.validator import validate_skill


def test_builtin_skills_valid() -> None:
    skills = load_all_skills(Path("skills/builtin"))
    assert len(skills) == 6
    for skill in skills:
        validation = validate_skill(skill)
        assert validation.valid, validation.errors
        assert len(skill.body.split()) >= 200
        assert skill.requires_tools
        assert skill.requires_permissions


def test_default_packs_valid() -> None:
    skills = {skill.skill_id for skill in load_all_skills(Path("skills/builtin"))}
    packs = load_all_packs(Path("skills/packs"))
    assert len(packs) == 3
    for pack in packs:
        assert pack.pack_id
        assert pack.skills
        for entry in pack.skills:
            assert entry.skill_id in skills


def test_default_packs_loadable_by_registry() -> None:
    registry = SkillRegistry(
        SkillsConfig(
            builtin_dir="skills/builtin",
            user_dir="skills/user",
            packs_dir="skills/packs",
        )
    )
    registry.load()
    assert registry.get_pack("caw.packs.deep_research") is not None
    assert registry.get_pack("caw.packs.adversarial_review") is not None
    assert registry.get_pack("caw.packs.workspace_ops") is not None
