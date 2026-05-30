import pytest

from caw.capabilities.deliberation.frames import FrameConfig
from caw.core.config import CAWConfig
from caw.errors import ValidationError_
from caw.skills.loader import SkillDocument
from caw.skills.registry import SkillRegistry


def test_frame_config_creation() -> None:
    frame = FrameConfig(frame_id="f1", skill_id="skill.one", label="Frame One")
    assert frame.frame_id == "f1"
    assert frame.skill_id == "skill.one"
    assert frame.label == "Frame One"


def test_frame_skill_resolution() -> None:
    registry = SkillRegistry(CAWConfig().skills)
    registry._skills["skill.one"] = SkillDocument(
        skill_id="skill.one",
        version="1.0.0",
        name="One",
        description="desc",
        author="test",
        body="Skill body",
    )
    frame = FrameConfig(frame_id="f1", skill_id="skill.one", label="Frame One")
    assert frame.resolve_skill(registry).body == "Skill body"


def test_frame_invalid_skill() -> None:
    registry = SkillRegistry(CAWConfig().skills)
    frame = FrameConfig(frame_id="f1", skill_id="missing", label="Frame One")
    with pytest.raises(ValidationError_, match="Invalid frame skill_id"):
        frame.resolve_skill(registry)
