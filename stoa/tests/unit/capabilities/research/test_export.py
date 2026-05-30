from pathlib import Path

import pytest

from caw.capabilities.research.export import ResearchExporter
from caw.capabilities.research.synthesize import SynthesisResult, SynthesizedClaim
from caw.core.config import CAWConfig
from caw.models import Session, SessionMode
from caw.storage.database import Database
from caw.storage.repository import ArtifactRepository, SessionRepository


@pytest.mark.asyncio
async def test_export_markdown(tmp_path: Path) -> None:
    db = Database(CAWConfig.model_validate({"storage": {"db_path": ":memory:"}}).storage)
    await db.connect()
    await db.run_migrations()
    session = Session(mode=SessionMode.RESEARCH)
    await SessionRepository(db).create(session)
    exporter = ResearchExporter(ArtifactRepository(db), tmp_path)
    result = SynthesisResult(
        query="q",
        claims=[SynthesizedClaim(text="Claim", citation_ids=["C1"])],
        uncertainty_markers=[],
        source_map={"C1": "Excerpt"},
        raw_output="",
        trace_id="t1",
    )
    artifact = await exporter.export(result, session.id, format="markdown")
    assert "Research Report" in Path(artifact.path or "").read_text()
    await db.close()


@pytest.mark.asyncio
async def test_export_json(tmp_path: Path) -> None:
    db = Database(CAWConfig.model_validate({"storage": {"db_path": ":memory:"}}).storage)
    await db.connect()
    await db.run_migrations()
    session = Session(mode=SessionMode.RESEARCH)
    await SessionRepository(db).create(session)
    exporter = ResearchExporter(ArtifactRepository(db), tmp_path)
    result = SynthesisResult(
        query="q",
        claims=[SynthesizedClaim(text="Claim", citation_ids=["C1"])],
        uncertainty_markers=[],
        source_map={"C1": "Excerpt"},
        raw_output="",
        trace_id="t1",
    )
    artifact = await exporter.export(result, session.id, format="json")
    assert '"claims"' in Path(artifact.path or "").read_text()
    await db.close()


@pytest.mark.asyncio
async def test_export_creates_artifact(tmp_path: Path) -> None:
    db = Database(CAWConfig.model_validate({"storage": {"db_path": ":memory:"}}).storage)
    await db.connect()
    await db.run_migrations()
    session = Session(mode=SessionMode.RESEARCH)
    await SessionRepository(db).create(session)
    repo = ArtifactRepository(db)
    exporter = ResearchExporter(repo, tmp_path)
    result = SynthesisResult(
        query="q",
        claims=[SynthesizedClaim(text="Claim", citation_ids=["C1"])],
        uncertainty_markers=[],
        source_map={"C1": "Excerpt"},
        raw_output="",
        trace_id="t1",
    )
    artifact = await exporter.export(result, session.id, format="markdown")
    assert await repo.get(artifact.id) is not None
    await db.close()
