import json

import pytest

from caw.capabilities.deliberation.engine import FrameOutput
from caw.capabilities.deliberation.rhetoric import RhetoricAnalysisEngine
from caw.core.config import CAWConfig
from caw.protocols.registry import ProviderRegistry
from caw.protocols.types import ProviderHealth, ProviderResponse
from caw.storage.database import Database
from caw.storage.repository import TraceEventRepository
from caw.traces.collector import TraceCollector


class StaticProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    @property
    def provider_id(self) -> str:
        return "primary"

    async def complete(
        self, messages, model, tools=None, max_tokens=4096, temperature=0.0, stream=False
    ):
        del messages, model, tools, max_tokens, temperature, stream
        return ProviderResponse(content=json.dumps(self._payload), model="mock-model")

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(available=True)

    def supports_tool_use(self) -> bool:
        return False

    def supports_streaming(self) -> bool:
        return False

    def max_context_window(self, model: str) -> int:
        del model
        return 1


async def _run(payload: dict[str, object]):
    config = CAWConfig.model_validate(
        {
            "providers": {
                "primary": {"type": "openai", "api_key_env": "OPENAI_API_KEY", "default_model": "m"}
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
    registry._providers["primary"] = StaticProvider(payload)
    engine = RhetoricAnalysisEngine(registry, collector)
    result = await engine.analyze(
        question="Q",
        frame_outputs=[FrameOutput(frame_id="f1", label="F1", position="text")],
        session_id="s1",
    )
    await collector.stop()
    return result


@pytest.mark.asyncio
async def test_rhetoric_devices_detected() -> None:
    result = await _run(
        {
            "devices": [
                {
                    "device_type": "false_dichotomy",
                    "frame_id": "f1",
                    "excerpt": "x",
                    "explanation": "y",
                    "severity": "cautionary",
                }
            ],
            "biases": [],
            "inconsistencies": [],
            "cross_frame_contradictions": [],
        }
    )
    assert result.devices[0].device_type == "false_dichotomy"


@pytest.mark.asyncio
async def test_rhetoric_biases_detected() -> None:
    result = await _run(
        {
            "devices": [],
            "biases": [
                {
                    "bias_type": "confirmation_bias",
                    "frame_id": "f1",
                    "excerpt": "x",
                    "explanation": "y",
                }
            ],
            "inconsistencies": [],
            "cross_frame_contradictions": [],
        }
    )
    assert result.biases[0].bias_type == "confirmation_bias"


@pytest.mark.asyncio
async def test_rhetoric_cross_frame_contradictions() -> None:
    result = await _run(
        {
            "devices": [],
            "biases": [],
            "inconsistencies": [],
            "cross_frame_contradictions": [
                {
                    "frame_a": "f1",
                    "frame_b": "f2",
                    "claim_a": "a",
                    "claim_b": "b",
                    "explanation": "oppose",
                }
            ],
        }
    )
    assert result.cross_frame_contradictions[0].frame_b == "f2"
