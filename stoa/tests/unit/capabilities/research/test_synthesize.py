import json

import pytest

from caw.capabilities.research.retrieve import RetrievalResult
from caw.capabilities.research.synthesize import Synthesizer
from caw.core.config import CAWConfig
from caw.protocols.mock import MockProvider
from caw.storage.database import Database
from caw.storage.repository import TraceEventRepository
from caw.traces.collector import TraceCollector


@pytest.mark.asyncio
async def test_synthesize_basic() -> None:
    payload = {
        "claims": [{"text": "Claim", "citation_ids": ["C1"], "confidence": 0.9}],
        "uncertainty_markers": [],
    }
    provider = MockProvider(response_text=json.dumps(payload))
    db = Database(CAWConfig.model_validate({"storage": {"db_path": ":memory:"}}).storage)
    await db.connect()
    await db.run_migrations()
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    await collector.start()
    result = await Synthesizer(provider, collector, model="mock").synthesize(
        "query", [RetrievalResult("s", "c", "evidence", 1.0)], session_id="s1"
    )
    await collector.stop()
    await db.close()
    assert result.claims


@pytest.mark.asyncio
async def test_synthesize_citations_linked() -> None:
    payload = {
        "claims": [{"text": "Claim", "citation_ids": ["C1"]}],
        "uncertainty_markers": [],
    }
    provider = MockProvider(response_text=json.dumps(payload))
    db = Database(CAWConfig.model_validate({"storage": {"db_path": ":memory:"}}).storage)
    await db.connect()
    await db.run_migrations()
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    await collector.start()
    result = await Synthesizer(provider, collector, model="mock").synthesize(
        "query", [RetrievalResult("s", "c", "evidence", 1.0)], session_id="s1"
    )
    await collector.stop()
    await db.close()
    assert all(citation in result.source_map for citation in result.claims[0].citation_ids)


@pytest.mark.asyncio
async def test_synthesize_uncertainty() -> None:
    payload = {
        "claims": [{"text": "Claim", "citation_ids": ["C1"]}],
        "uncertainty_markers": ["Sources disagree on timeline"],
    }
    provider = MockProvider(response_text=json.dumps(payload))
    db = Database(CAWConfig.model_validate({"storage": {"db_path": ":memory:"}}).storage)
    await db.connect()
    await db.run_migrations()
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    await collector.start()
    result = await Synthesizer(provider, collector, model="mock").synthesize(
        "query",
        [RetrievalResult("s", "c", "source A", 1.0), RetrievalResult("s", "d", "source B", 0.9)],
        session_id="s1",
    )
    await collector.stop()
    await db.close()
    assert result.uncertainty_markers
