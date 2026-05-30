from pathlib import Path

import pytest

from caw.capabilities.research.ingest import IngestPipeline, SourceInput
from caw.core.config import CAWConfig
from caw.storage.database import Database
from caw.storage.repository import SourceRepository, TraceEventRepository
from caw.traces.collector import TraceCollector


@pytest.fixture
async def ingest_stack() -> tuple[Database, IngestPipeline, SourceRepository, TraceCollector]:
    config = CAWConfig.model_validate({"storage": {"db_path": ":memory:"}})
    db = Database(config.storage)
    await db.connect()
    await db.run_migrations()
    source_repo = SourceRepository(db)
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    await collector.start()
    pipeline = IngestPipeline(source_repo, db, collector, chunk_size=10, chunk_overlap=2)
    yield db, pipeline, source_repo, collector
    await collector.stop()
    await db.close()


@pytest.mark.asyncio
async def test_ingest_text_file(
    ingest_stack: tuple[Database, IngestPipeline, SourceRepository, TraceCollector],
) -> None:
    _, pipeline, source_repo, _ = ingest_stack
    path = Path("tests/fixtures/research/sample.txt")
    source = await pipeline.ingest(SourceInput(session_id="s1", path=path))
    stored = await source_repo.get(source.id)
    assert stored is not None
    assert "sample text file" in (stored.content or "")


@pytest.mark.asyncio
async def test_ingest_markdown(
    ingest_stack: tuple[Database, IngestPipeline, SourceRepository, TraceCollector],
) -> None:
    _, pipeline, _, _ = ingest_stack
    source = await pipeline.ingest(
        SourceInput(session_id="s1", path=Path("tests/fixtures/research/sample.md"))
    )
    assert source.type == "md"
    assert "Sample Markdown" in (source.content or "")


@pytest.mark.asyncio
async def test_ingest_pdf(
    ingest_stack: tuple[Database, IngestPipeline, SourceRepository, TraceCollector],
) -> None:
    _, pipeline, _, _ = ingest_stack
    source = await pipeline.ingest(
        SourceInput(session_id="s1", path=Path("tests/fixtures/research/sample.pdf"))
    )
    assert "renewable energy" in (source.content or "")


@pytest.mark.asyncio
async def test_chunking(
    ingest_stack: tuple[Database, IngestPipeline, SourceRepository, TraceCollector],
) -> None:
    db, pipeline, source_repo, _ = ingest_stack
    text = " ".join(f"token{i}" for i in range(40))
    source = await pipeline.ingest(SourceInput(session_id="s1", text=text, title="large"))
    assert await source_repo.get(source.id) is not None
    rows = await (
        await db.connection().execute(
            "SELECT content FROM source_chunks WHERE source_id = ? ORDER BY chunk_index",
            (source.id,),
        )
    ).fetchall()
    assert len(rows) > 1
    first_words = str(rows[0]["content"]).split()
    second_words = str(rows[1]["content"]).split()
    assert first_words[-2:] == second_words[:2]


@pytest.mark.asyncio
async def test_duplicate_detection(
    ingest_stack: tuple[Database, IngestPipeline, SourceRepository, TraceCollector],
) -> None:
    _, pipeline, _, _ = ingest_stack
    path = Path("tests/fixtures/research/sample.txt")
    first = await pipeline.ingest(SourceInput(session_id="s1", path=path))
    second = await pipeline.ingest(SourceInput(session_id="s1", path=path))
    assert first.id == second.id


@pytest.mark.asyncio
async def test_content_hash(
    ingest_stack: tuple[Database, IngestPipeline, SourceRepository, TraceCollector],
) -> None:
    _, pipeline, _, _ = ingest_stack
    source = await pipeline.ingest(
        SourceInput(session_id="s1", path=Path("tests/fixtures/research/sample.txt"))
    )
    assert source.content_hash is not None
    assert len(source.content_hash) == 64
