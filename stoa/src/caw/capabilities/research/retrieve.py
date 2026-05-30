"""Keyword retrieval for ingested research chunks."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING

from caw.models import TraceEvent

if TYPE_CHECKING:
    from caw.storage.database import Database
    from caw.traces.collector import TraceCollector


@dataclass(slots=True)
class RetrievalResult:
    source_id: str
    chunk_id: str
    content: str
    relevance_score: float


class Retriever:
    """Retrieve relevant chunks using SQLite FTS5 keyword search."""

    def __init__(self, database: Database, trace_collector: TraceCollector) -> None:
        self._database = database
        self._trace_collector = trace_collector

    async def retrieve(
        self,
        query: str,
        session_id: str,
        strategy: str = "hybrid",
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[RetrievalResult]:
        if not query.strip():
            return []

        trace_id = sha256(f"retrieve:{session_id}:{query}".encode()).hexdigest()
        await self._trace_collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="retrieval:started",
                data={"query": query, "strategy": strategy, "top_k": top_k},
            )
        )

        if strategy not in {"keyword", "hybrid", "semantic"}:
            strategy = "keyword"

        conn = self._database.connection()
        rows = await (
            await conn.execute(
                "SELECT chunk_id, source_id, content, bm25(source_chunks_fts) AS rank "
                "FROM source_chunks_fts WHERE source_chunks_fts MATCH ? AND session_id = ? "
                "ORDER BY rank LIMIT ?",
                (query, session_id, top_k),
            )
        ).fetchall()

        results: list[RetrievalResult] = []
        for row in rows:
            rank = float(row["rank"])
            score = -rank
            if score < min_score:
                continue
            results.append(
                RetrievalResult(
                    source_id=str(row["source_id"]),
                    chunk_id=str(row["chunk_id"]),
                    content=str(row["content"]),
                    relevance_score=score,
                )
            )

        await self._trace_collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="retrieval:results",
                data={"result_count": len(results), "source_ids": [r.source_id for r in results]},
            )
        )
        return results
