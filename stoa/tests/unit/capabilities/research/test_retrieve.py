import pytest

from caw.capabilities.research.ingest import IngestPipeline, SourceInput
from caw.capabilities.research.retrieve import Retriever
from caw.core.config import CAWConfig
from caw.storage.database import Database
from caw.storage.repository import SourceRepository, TraceEventRepository
from caw.traces.collector import TraceCollector


@pytest.mark.asyncio
async def test_retrieve_keyword_match() -> None:
    config = CAWConfig.model_validate({"storage": {"db_path": ":memory:"}})
    db = Database(config.storage)
    await db.connect()
    await db.run_migrations()
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    await collector.start()
    pipeline = IngestPipeline(SourceRepository(db), db, collector)
    await pipeline.ingest(SourceInput(session_id="s1", text="alpha beta gamma climate"))
    results = await Retriever(db, collector).retrieve("climate", "s1")
    await collector.stop()
    await db.close()
    assert results
    assert "climate" in results[0].content


@pytest.mark.asyncio
async def test_retrieve_no_match() -> None:
    config = CAWConfig.model_validate({"storage": {"db_path": ":memory:"}})
    db = Database(config.storage)
    await db.connect()
    await db.run_migrations()
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    await collector.start()
    pipeline = IngestPipeline(SourceRepository(db), db, collector)
    await pipeline.ingest(SourceInput(session_id="s1", text="alpha beta gamma"))
    results = await Retriever(db, collector).retrieve("delta", "s1")
    await collector.stop()
    await db.close()
    assert results == []


@pytest.mark.asyncio
async def test_retrieve_top_k() -> None:
    config = CAWConfig.model_validate({"storage": {"db_path": ":memory:"}})
    db = Database(config.storage)
    await db.connect()
    await db.run_migrations()
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    await collector.start()
    pipeline = IngestPipeline(SourceRepository(db), db, collector, chunk_size=3, chunk_overlap=0)
    await pipeline.ingest(
        SourceInput(session_id="s1", text="topic topic topic one two three four five six")
    )
    results = await Retriever(db, collector).retrieve("topic", "s1", top_k=1)
    await collector.stop()
    await db.close()
    assert len(results) == 1


@pytest.mark.asyncio
async def test_retrieve_provenance() -> None:
    config = CAWConfig.model_validate({"storage": {"db_path": ":memory:"}})
    db = Database(config.storage)
    await db.connect()
    await db.run_migrations()
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    await collector.start()
    pipeline = IngestPipeline(SourceRepository(db), db, collector)
    await pipeline.ingest(SourceInput(session_id="s1", text="policy policy policy"))
    results = await Retriever(db, collector).retrieve("policy", "s1")
    await collector.stop()
    await db.close()
    assert all(result.source_id for result in results)
