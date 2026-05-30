"""Rhetoric analysis for deliberation outputs."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from caw.errors import ProviderError
from caw.models import TraceEvent
from caw.protocols.types import ProviderMessage, ProviderResponse

if TYPE_CHECKING:
    from caw.capabilities.deliberation.engine import FrameOutput
    from caw.protocols.registry import ProviderRegistry
    from caw.traces.collector import TraceCollector


@dataclass(slots=True)
class RhetoricalDevice:
    device_type: str
    frame_id: str
    excerpt: str
    explanation: str
    severity: str


@dataclass(slots=True)
class IdentifiedBias:
    bias_type: str
    frame_id: str
    excerpt: str
    explanation: str


@dataclass(slots=True)
class Inconsistency:
    frame_id: str
    claim_a: str
    claim_b: str
    explanation: str


@dataclass(slots=True)
class Contradiction:
    frame_a: str
    frame_b: str
    claim_a: str
    claim_b: str
    explanation: str


@dataclass(slots=True)
class RhetoricAnalysis:
    devices: list[RhetoricalDevice]
    biases: list[IdentifiedBias]
    inconsistencies: list[Inconsistency]
    cross_frame_contradictions: list[Contradiction]


class RhetoricAnalysisEngine:
    """Use a provider call to detect rhetorical patterns and contradictions."""

    def __init__(
        self, provider_registry: ProviderRegistry, trace_collector: TraceCollector
    ) -> None:
        self._provider_registry = provider_registry
        self._trace_collector = trace_collector

    async def analyze(
        self,
        question: str,
        frame_outputs: list[FrameOutput],
        session_id: str,
    ) -> RhetoricAnalysis:
        provider_key = self._provider_registry.list_providers()[0]
        provider = self._provider_registry.get(provider_key)
        trace_id = str(uuid.uuid4())

        frame_payload = [
            {"frame_id": output.frame_id, "label": output.label, "position": output.position}
            for output in frame_outputs
        ]
        prompt = (
            "Analyze the provided frame outputs for rhetorical devices, biases, internal "
            "inconsistencies, and cross-frame contradictions. Return strict JSON with keys: "
            "devices, biases, inconsistencies, cross_frame_contradictions."
            f"\nQuestion: {question}\nFrames: {json.dumps(frame_payload)}"
        )
        response = await provider.complete(
            messages=[ProviderMessage(role="user", content=prompt)],
            model="mock-model",
        )
        if not isinstance(response, ProviderResponse):
            raise ProviderError(
                message="Rhetoric analysis requires non-streaming provider responses.",
                code="deliberation_streaming_not_supported",
            )
        raw = (
            response.content if isinstance(response.content, str) else json.dumps(response.content)
        )
        parsed = json.loads(raw)

        await self._trace_collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="deliberation:rhetoric",
                data={
                    "devices": len(parsed.get("devices", [])),
                    "biases": len(parsed.get("biases", [])),
                    "inconsistencies": len(parsed.get("inconsistencies", [])),
                    "cross_frame_contradictions": len(parsed.get("cross_frame_contradictions", [])),
                },
            )
        )

        return RhetoricAnalysis(
            devices=[RhetoricalDevice(**item) for item in parsed.get("devices", [])],
            biases=[IdentifiedBias(**item) for item in parsed.get("biases", [])],
            inconsistencies=[Inconsistency(**item) for item in parsed.get("inconsistencies", [])],
            cross_frame_contradictions=[
                Contradiction(**item) for item in parsed.get("cross_frame_contradictions", [])
            ],
        )
