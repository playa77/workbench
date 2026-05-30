from datetime import UTC, datetime

import pytest

from caw.core.config import StorageConfig
from caw.evaluation.comparator import Comparator
from caw.models import EvalRun
from caw.storage.database import Database
from caw.storage.repository import EvalRunRepository


@pytest.mark.asyncio
async def test_compare_two_runs() -> None:
    database = Database(StorageConfig(db_path=":memory:"))
    await database.connect()
    await database.run_migrations()
    repo = EvalRunRepository(database)

    now = datetime.now(UTC)
    run_a = await repo.create(
        EvalRun(
            task_id="t",
            provider="p",
            model="m",
            started_at=now,
            status="completed",
            scores={"latency": 0.7},
        )
    )
    run_b = await repo.create(
        EvalRun(
            task_id="t",
            provider="p",
            model="m",
            started_at=now,
            status="completed",
            scores={"latency": 0.9},
        )
    )

    result = await Comparator(repo).compare([run_a.id, run_b.id])
    assert result.dimensions == ["latency"]
    assert result.matrix[run_a.id]["latency"] == 0.7

    await database.close()
