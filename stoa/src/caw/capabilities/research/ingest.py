"""Source ingestion pipeline for the research capability."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup
from markdownify import markdownify
from pypdf import PdfReader

from caw.errors import ValidationError_
from caw.models import Source, TraceEvent

if TYPE_CHECKING:
    from pathlib import Path

    from caw.storage.database import Database
    from caw.storage.repository import SourceRepository
    from caw.traces.collector import TraceCollector


@dataclass(slots=True)
class SourceInput:
    """Input descriptor for source ingestion."""

    session_id: str
    path: Path | None = None
    text: str | None = None
    uri: str | None = None
    title: str | None = None


class IngestPipeline:
    """Ingests sources, chunks content, and persists chunk indexes."""

    def __init__(
        self,
        source_repo: SourceRepository,
        database: Database,
        trace_collector: TraceCollector,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> None:
        self._source_repo = source_repo
        self._database = database
        self._trace_collector = trace_collector
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    async def ingest(self, source: SourceInput) -> Source:
        trace_id = hashlib.sha256(
            f"{source.session_id}:{source.path}:{source.uri}".encode()
        ).hexdigest()
        await self._trace_collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=source.session_id,
                event_type="ingestion:started",
                data={"path": str(source.path) if source.path else None, "uri": source.uri},
            )
        )

        source_type = self._detect_type(source)
        content = self._extract_content(source, source_type)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        duplicate = await self._source_repo.find_by_hash(content_hash)
        if duplicate is not None:
            await self._trace_collector.emit(
                TraceEvent(
                    trace_id=trace_id,
                    session_id=source.session_id,
                    event_type="ingestion:skipped_duplicate",
                    data={"source_id": duplicate.id, "content_hash": content_hash},
                )
            )
            return duplicate

        stored_source = await self._source_repo.create(
            Source(
                session_id=source.session_id,
                type=source_type,
                uri=str(source.path) if source.path else source.uri,
                title=source.title or (source.path.name if source.path else source.uri),
                content=content,
                content_hash=content_hash,
            )
        )

        chunks = self._chunk_content(content)
        await self._store_chunks(stored_source.id, source.session_id, chunks)

        await self._trace_collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=source.session_id,
                event_type="ingestion:completed",
                data={"source_id": stored_source.id, "chunk_count": len(chunks)},
            )
        )
        return stored_source

    async def ingest_batch(self, sources: list[SourceInput]) -> list[Source]:
        return [await self.ingest(source) for source in sources]

    def _detect_type(self, source: SourceInput) -> str:
        if source.path is None:
            return "text"
        suffix = source.path.suffix.lower()
        supported = {".txt", ".md", ".pdf", ".html", ".csv", ".json"}
        if suffix not in supported:
            raise ValidationError_(
                message=f"Unsupported source type: {suffix}", code="unsupported_source"
            )
        return suffix.lstrip(".")

    def _extract_content(self, source: SourceInput, source_type: str) -> str:
        if source.text is not None:
            return source.text
        if source.path is None:
            raise ValidationError_(
                message="Source must include either path or text", code="invalid_source"
            )

        if source_type in {"txt", "md"}:
            return source.path.read_text(encoding="utf-8")
        if source_type == "pdf":
            return self._extract_pdf(source.path)
        if source_type == "html":
            html = source.path.read_text(encoding="utf-8")
            return self._extract_html(html)
        if source_type == "csv":
            with source.path.open("r", encoding="utf-8", newline="") as handle:
                rows = [", ".join(row) for row in csv.reader(handle)]
            return "\n".join(rows)
        if source_type == "json":
            payload = json.loads(source.path.read_text(encoding="utf-8"))
            return json.dumps(payload, indent=2, sort_keys=True)
        raise ValidationError_(
            message=f"Unsupported source type: {source_type}", code="unsupported_source"
        )

    def _extract_pdf(self, path: Path) -> str:
        try:
            reader = PdfReader(str(path))
            extracted = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
            if extracted:
                return extracted
        except Exception:
            pass
        return path.read_text(encoding="utf-8")

    def _extract_html(self, html: str) -> str:
        markdown = markdownify(html)
        soup = BeautifulSoup(markdown, "html.parser")
        return soup.get_text("\n").strip()

    def _chunk_content(self, content: str) -> list[str]:
        words = content.split()
        if not words:
            return []
        chunks: list[str] = []
        step = max(1, self._chunk_size - self._chunk_overlap)
        for start in range(0, len(words), step):
            segment = words[start : start + self._chunk_size]
            if not segment:
                continue
            chunks.append(" ".join(segment))
            if start + self._chunk_size >= len(words):
                break
        return chunks

    async def _store_chunks(self, source_id: str, session_id: str, chunks: list[str]) -> None:
        conn = self._database.connection()
        for idx, chunk in enumerate(chunks):
            chunk_id = hashlib.sha256(f"{source_id}:{idx}".encode()).hexdigest()
            metadata: dict[str, Any] = {"chunk_index": idx}
            await conn.execute(
                (
                    "INSERT INTO source_chunks (id, source_id, session_id, chunk_index, content, "
                    "token_count, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    chunk_id,
                    source_id,
                    session_id,
                    idx,
                    chunk,
                    len(chunk.split()),
                    json.dumps(metadata),
                ),
            )
            await conn.execute(
                (
                    "INSERT INTO source_chunks_fts (content, chunk_id, source_id, session_id) "
                    "VALUES (?, ?, ?, ?)"
                ),
                (chunk, chunk_id, source_id, session_id),
            )
        await conn.commit()
