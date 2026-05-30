"""Deliberation engine for structured multi-frame reasoning."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from caw.capabilities.deliberation.rhetoric import RhetoricAnalysis, RhetoricAnalysisEngine
from caw.errors import ProviderError
from caw.models import TraceEvent
from caw.protocols.types import ProviderMessage, ProviderResponse

if TYPE_CHECKING:
    from caw.capabilities.deliberation.frames import FrameConfig
    from caw.protocols.registry import ProviderRegistry
    from caw.skills.registry import SkillRegistry
    from caw.traces.collector import TraceCollector


@dataclass(slots=True)
class CritiqueResponse:
    from_frame: str
    to_frame: str
    content: str


@dataclass(slots=True)
class FrameOutput:
    frame_id: str
    label: str
    position: str
    critiques: list[CritiqueResponse] = field(default_factory=list)


@dataclass(slots=True)
class AgreementPoint:
    claim: str
    supporting_frames: list[str]


@dataclass(slots=True)
class DisagreementPoint:
    claim: str
    frame_positions: dict[str, str]


@dataclass(slots=True)
class DisagreementSurface:
    agreements: list[AgreementPoint]
    disagreements: list[DisagreementPoint]
    open_questions: list[str]
    confidence_map: dict[str, float]


@dataclass(slots=True)
class DeliberationResult:
    question: str
    frames: list[FrameOutput]
    rhetoric_analysis: RhetoricAnalysis | None
    disagreement_surface: DisagreementSurface
    synthesis: str | None
    trace_id: str


class DeliberationEngine:
    """Orchestrate multi-frame generation, critique, analysis, and synthesis."""

    def __init__(
        self,
        provider_registry: ProviderRegistry,
        skill_registry: SkillRegistry,
        trace_collector: TraceCollector,
    ) -> None:
        self._provider_registry = provider_registry
        self._skill_registry = skill_registry
        self._trace_collector = trace_collector
        self._rhetoric_engine = RhetoricAnalysisEngine(provider_registry, trace_collector)

    async def deliberate(
        self,
        question: str,
        frames: list[FrameConfig],
        rounds: int = 2,
        include_rhetoric_analysis: bool = True,
        include_synthesis: bool = True,
        session_id: str = "deliberation",
    ) -> DeliberationResult:
        trace_id = str(uuid.uuid4())
        await self._trace_collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="deliberation:started",
                data={"question": question, "frame_count": len(frames), "rounds": rounds},
            )
        )

        outputs: list[FrameOutput] = []
        for frame in frames:
            skill = frame.resolve_skill(self._skill_registry)
            position = await self._call_frame(frame, question, skill.body)
            outputs.append(
                FrameOutput(frame_id=frame.frame_id, label=frame.label, position=position)
            )
            await self._trace_collector.emit(
                TraceEvent(
                    trace_id=trace_id,
                    session_id=session_id,
                    event_type="deliberation:frame_output",
                    data={"frame_id": frame.frame_id, "position_summary": position[:120]},
                )
            )

        for _round in range(rounds):
            for source in outputs:
                for target in outputs:
                    if source.frame_id == target.frame_id:
                        continue
                    critique = await self._call_critique(source, target, question)
                    source.critiques.append(
                        CritiqueResponse(
                            from_frame=source.frame_id,
                            to_frame=target.frame_id,
                            content=critique,
                        )
                    )
                    await self._trace_collector.emit(
                        TraceEvent(
                            trace_id=trace_id,
                            session_id=session_id,
                            event_type="deliberation:critique",
                            data={
                                "from_frame": source.frame_id,
                                "to_frame": target.frame_id,
                                "critique_summary": critique[:120],
                            },
                        )
                    )

        rhetoric_analysis = None
        if include_rhetoric_analysis:
            rhetoric_analysis = await self._rhetoric_engine.analyze(
                question=question,
                frame_outputs=outputs,
                session_id=session_id,
            )

        surface = self._build_surface(question, outputs)
        synthesis = None
        if include_synthesis:
            synthesis = self._build_synthesis(outputs, surface)

        await self._trace_collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="deliberation:completed",
                data={
                    "agreement_count": len(surface.agreements),
                    "disagreement_count": len(surface.disagreements),
                },
            )
        )

        return DeliberationResult(
            question=question,
            frames=outputs,
            rhetoric_analysis=rhetoric_analysis,
            disagreement_surface=surface,
            synthesis=synthesis,
            trace_id=trace_id,
        )

    def _content_text(self, response: ProviderResponse | object) -> str:
        if not isinstance(response, ProviderResponse):
            raise ProviderError(
                message="Deliberation requires non-streaming provider responses.",
                code="deliberation_streaming_not_supported",
            )
        return (
            response.content if isinstance(response.content, str) else json.dumps(response.content)
        )

    async def _call_frame(self, frame: FrameConfig, question: str, skill_body: str) -> str:
        provider_id = frame.provider or self._provider_registry.list_providers()[0]
        provider = self._provider_registry.get(provider_id)
        model = frame.model or "mock-model"
        context = f"\nAdditional context: {frame.initial_context}" if frame.initial_context else ""
        prompt = (
            f"Frame: {frame.label}\n"
            f"Skill guidance:\n{skill_body}\n{context}\n"
            f"Question: {question}\n"
            "Provide this frame's initial position."
        )
        response = await provider.complete(
            messages=[ProviderMessage(role="user", content=prompt)],
            model=model,
        )
        return self._content_text(response)

    async def _call_critique(self, source: FrameOutput, target: FrameOutput, question: str) -> str:
        provider_id = self._provider_registry.list_providers()[0]
        provider = self._provider_registry.get(provider_id)
        model = "mock-model"
        prompt = (
            f"Question: {question}\n"
            f"Your frame position:\n{source.position}\n"
            f"Other frame ({target.label}) position:\n{target.position}\n"
            "Provide a concise critique of the other frame's position."
        )
        response = await provider.complete(
            messages=[ProviderMessage(role="user", content=prompt)],
            model=model,
        )
        return self._content_text(response)

    def _build_surface(self, question: str, outputs: list[FrameOutput]) -> DisagreementSurface:
        agreements: list[AgreementPoint] = []
        if outputs and len({item.position.strip() for item in outputs}) == 1:
            agreements.append(
                AgreementPoint(
                    claim=outputs[0].position.strip()[:120],
                    supporting_frames=[item.frame_id for item in outputs],
                )
            )

        disagreements: list[DisagreementPoint] = []
        if len({item.position.strip() for item in outputs}) > 1:
            disagreements.append(
                DisagreementPoint(
                    claim=question,
                    frame_positions={item.frame_id: item.position for item in outputs},
                )
            )

        return DisagreementSurface(
            agreements=agreements,
            disagreements=disagreements,
            open_questions=[] if disagreements else [question],
            confidence_map={question: 0.5},
        )

    def _build_synthesis(self, outputs: list[FrameOutput], surface: DisagreementSurface) -> str:
        frame_labels = ", ".join(output.label for output in outputs)
        return (
            f"Synthesized view across frames: {frame_labels}. "
            f"Agreements: {len(surface.agreements)}, "
            f"disagreements: {len(surface.disagreements)}."
        )
