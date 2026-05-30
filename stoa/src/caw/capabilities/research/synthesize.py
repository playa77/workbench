"""Synthesis stage for citation-aware research outputs."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from caw.models import TraceEvent
from caw.protocols.types import ProviderMessage

if TYPE_CHECKING:
    from caw.capabilities.research.retrieve import RetrievalResult
    from caw.protocols.provider import ModelProvider
    from caw.skills.resolver import ResolvedSkill
    from caw.traces.collector import TraceCollector


@dataclass
class SynthesizedClaim:
    text: str
    citation_ids: list[str]
    confidence: float | None = None


@dataclass
class SynthesisResult:
    query: str
    claims: list[SynthesizedClaim]
    uncertainty_markers: list[str]
    source_map: dict[str, str]
    raw_output: str
    trace_id: str


class Synthesizer:
    """Generate structured, citation-linked synthesis from retrieval results."""

    def __init__(
        self,
        provider: ModelProvider,
        trace_collector: TraceCollector,
        model: str,
    ) -> None:
        self._provider = provider
        self._trace_collector = trace_collector
        self._model = model

    async def synthesize(
        self,
        query: str,
        retrieval_results: list[RetrievalResult],
        output_format: str = "structured",
        active_skills: list[ResolvedSkill] | None = None,
        session_id: str = "",
    ) -> SynthesisResult:
        del active_skills
        trace_id = str(uuid.uuid4())
        await self._trace_collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="synthesis:started",
                data={
                    "query": query,
                    "source_count": len(retrieval_results),
                    "format": output_format,
                },
            )
        )

        source_map = {f"C{idx + 1}": result.content for idx, result in enumerate(retrieval_results)}
        prompt = {
            "query": query,
            "format": output_format,
            "sources": [
                {"citation_id": cid, "excerpt": excerpt} for cid, excerpt in source_map.items()
            ],
        }
        response = await self._provider.complete(
            messages=[ProviderMessage(role="user", content=json.dumps(prompt))],
            model=self._model,
        )
        raw_output = "" if not isinstance(response.content, str) else response.content

        claims, uncertainty = self._parse_output(raw_output, source_map)

        await self._trace_collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="synthesis:completed",
                data={"claim_count": len(claims), "uncertainty_count": len(uncertainty)},
            )
        )

        return SynthesisResult(
            query=query,
            claims=claims,
            uncertainty_markers=uncertainty,
            source_map=source_map,
            raw_output=raw_output,
            trace_id=trace_id,
        )

    def _parse_output(
        self,
        raw_output: str,
        source_map: dict[str, str],
    ) -> tuple[list[SynthesizedClaim], list[str]]:
        default_citation = next(iter(source_map.keys()), "")
        try:
            parsed = json.loads(raw_output)
            claim_rows = parsed.get("claims", []) if isinstance(parsed, dict) else []
            uncertainty = parsed.get("uncertainty_markers", []) if isinstance(parsed, dict) else []
            claims: list[SynthesizedClaim] = []
            for row in claim_rows:
                if not isinstance(row, dict):
                    continue
                citations = [c for c in row.get("citation_ids", []) if c in source_map]
                if not citations and default_citation:
                    citations = [default_citation]
                claims.append(
                    SynthesizedClaim(
                        text=str(row.get("text", "")),
                        citation_ids=citations,
                        confidence=float(row["confidence"]) if "confidence" in row else None,
                    )
                )
            return claims, [str(item) for item in uncertainty]
        except json.JSONDecodeError:
            citation_ids = [default_citation] if default_citation else []
            return [SynthesizedClaim(text=raw_output, citation_ids=citation_ids)], []
