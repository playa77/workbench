"""Export synthesis results into user-facing artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from caw.models import Artifact, ArtifactType

if TYPE_CHECKING:
    from pathlib import Path

    from caw.capabilities.research.synthesize import SynthesisResult
    from caw.storage.repository import ArtifactRepository


class ResearchExporter:
    """Persist synthesis outputs as Markdown or JSON artifacts."""

    def __init__(self, artifact_repo: ArtifactRepository, artifact_dir: Path) -> None:
        self._artifact_repo = artifact_repo
        self._artifact_dir = artifact_dir

    async def export(
        self,
        synthesis: SynthesisResult,
        session_id: str,
        format: str = "markdown",
        name: str = "research_report",
    ) -> Artifact:
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        if format == "json":
            content = self._render_json(synthesis)
            extension = "json"
        else:
            content = self._render_markdown(synthesis)
            extension = "md"

        output_path = self._artifact_dir / f"{name}.{extension}"
        output_path.write_text(content, encoding="utf-8")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        artifact = Artifact(
            session_id=session_id,
            type=ArtifactType.EXPORT,
            name=output_path.name,
            path=str(output_path),
            content=content,
            content_hash=content_hash,
            metadata={"format": format, "trace_id": synthesis.trace_id},
        )
        return await self._artifact_repo.create(artifact)

    def _render_markdown(self, synthesis: SynthesisResult) -> str:
        lines = ["# Research Report", "", f"Query: {synthesis.query}", "", "## Claims"]
        for idx, claim in enumerate(synthesis.claims, start=1):
            citations = " ".join(f"[{cid}]" for cid in claim.citation_ids)
            lines.append(f"{idx}. {claim.text} {citations}".strip())
        lines.append("")
        lines.append("## Evidence Map")
        for cid, excerpt in synthesis.source_map.items():
            lines.append(f"- {cid}: {excerpt}")
        if synthesis.uncertainty_markers:
            lines.append("")
            lines.append("## Uncertainty")
            for marker in synthesis.uncertainty_markers:
                lines.append(f"- {marker}")
        return "\n".join(lines)

    def _render_json(self, synthesis: SynthesisResult) -> str:
        payload = {
            "query": synthesis.query,
            "claims": [
                {
                    "text": claim.text,
                    "citation_ids": claim.citation_ids,
                    "confidence": claim.confidence,
                }
                for claim in synthesis.claims
            ],
            "uncertainty_markers": synthesis.uncertainty_markers,
            "source_map": synthesis.source_map,
            "trace_id": synthesis.trace_id,
        }
        return json.dumps(payload, indent=2)
