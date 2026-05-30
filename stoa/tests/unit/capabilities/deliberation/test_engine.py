import json

import pytest

from caw.capabilities.deliberation.engine import DeliberationEngine
from caw.capabilities.deliberation.frames import FrameConfig
from caw.core.config import CAWConfig
from caw.protocols.registry import ProviderRegistry
from caw.protocols.types import ProviderHealth, ProviderResponse
from caw.skills.loader import SkillDocument
from caw.skills.registry import SkillRegistry
from caw.storage.database import Database
from caw.storage.repository import TraceEventRepository
from caw.traces.collector import TraceCollector


class SequencedProvider:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self._index = 0

    @property
    def provider_id(self) -> str:
        return "primary"

    async def complete(
        self, messages, model, tools=None, max_tokens=4096, temperature=0.0, stream=False
    ):
        del messages, model, tools, max_tokens, temperature, stream
        text = self._responses[self._index]
        self._index += 1
        return ProviderResponse(content=text, model="mock-model")

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(available=True)

    def supports_tool_use(self) -> bool:
        return False

    def supports_streaming(self) -> bool:
        return False

    def max_context_window(self, model: str) -> int:
        del model
        return 8192


async def _build_engine(
    responses: list[str],
) -> tuple[DeliberationEngine, TraceCollector, SkillRegistry]:
    config = CAWConfig.model_validate(
        {
            "providers": {
                "primary": {
                    "type": "openai",
                    "api_key_env": "OPENAI_API_KEY",
                    "default_model": "gpt-4o-mini",
                }
            },
            "storage": {"db_path": ":memory:"},
        }
    )
    db = Database(config.storage)
    await db.connect()
    await db.run_migrations()
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    await collector.start()

    registry = ProviderRegistry(config)
    registry._providers["primary"] = SequencedProvider(responses)

    skill_registry = SkillRegistry(config.skills)
    skill_registry._skills["skill.a"] = SkillDocument(
        skill_id="skill.a", version="1", name="A", description="", author="", body="A body"
    )
    skill_registry._skills["skill.b"] = SkillDocument(
        skill_id="skill.b", version="1", name="B", description="", author="", body="B body"
    )

    return DeliberationEngine(registry, skill_registry, collector), collector, skill_registry


@pytest.mark.asyncio
async def test_deliberate_two_frames() -> None:
    rhetoric = json.dumps(
        {"devices": [], "biases": [], "inconsistencies": [], "cross_frame_contradictions": []}
    )
    engine, collector, _ = await _build_engine(
        ["Position A", "Position B", "Crit A", "Crit B", rhetoric]
    )
    result = await engine.deliberate(
        "Question?",
        [
            FrameConfig(frame_id="a", skill_id="skill.a", label="A"),
            FrameConfig(frame_id="b", skill_id="skill.b", label="B"),
        ],
        rounds=1,
    )
    await collector.stop()
    assert len(result.frames) == 2
    assert {frame.frame_id for frame in result.frames} == {"a", "b"}


@pytest.mark.asyncio
async def test_deliberate_critique_round() -> None:
    rhetoric = json.dumps(
        {"devices": [], "biases": [], "inconsistencies": [], "cross_frame_contradictions": []}
    )
    engine, collector, _ = await _build_engine(["A", "B", "A->B", "B->A", rhetoric])
    result = await engine.deliberate(
        "Question?",
        [
            FrameConfig(frame_id="a", skill_id="skill.a", label="A"),
            FrameConfig(frame_id="b", skill_id="skill.b", label="B"),
        ],
        rounds=1,
    )
    await collector.stop()
    assert all(frame.critiques for frame in result.frames)


@pytest.mark.asyncio
async def test_deliberate_disagreement_surface() -> None:
    rhetoric = json.dumps(
        {"devices": [], "biases": [], "inconsistencies": [], "cross_frame_contradictions": []}
    )
    engine, collector, _ = await _build_engine(["A", "B", "A->B", "B->A", rhetoric])
    result = await engine.deliberate(
        "Question?",
        [
            FrameConfig(frame_id="a", skill_id="skill.a", label="A"),
            FrameConfig(frame_id="b", skill_id="skill.b", label="B"),
        ],
        rounds=1,
    )
    await collector.stop()
    assert result.disagreement_surface.disagreements


@pytest.mark.asyncio
async def test_deliberate_zero_rounds() -> None:
    rhetoric = json.dumps(
        {"devices": [], "biases": [], "inconsistencies": [], "cross_frame_contradictions": []}
    )
    engine, collector, _ = await _build_engine(["A", "B", rhetoric])
    result = await engine.deliberate(
        "Question?",
        [
            FrameConfig(frame_id="a", skill_id="skill.a", label="A"),
            FrameConfig(frame_id="b", skill_id="skill.b", label="B"),
        ],
        rounds=0,
    )
    await collector.stop()
    assert len(result.frames) == 2
    assert sum(len(frame.critiques) for frame in result.frames) == 0
