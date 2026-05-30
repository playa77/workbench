from datetime import UTC, datetime

import pytest

from caw.core.config import StorageConfig
from caw.evaluation.regression import RegressionDetector
from caw.models import EvalRun
from caw.storage.database import Database
from caw.storage.repository import EvalRunRepository


async def _insert_values(repo: EvalRunRepository, values: list[float]) -> str:
    latest_id = ""
    now = datetime.now(UTC)
    for value in values:
        run = await repo.create(
            EvalRun(
                task_id="t",
                provider="p",
                model="m",
                started_at=now,
                status="completed",
                scores={"composite": value},
            )
        )
        latest_id = run.id
    return latest_id


@pytest.mark.asyncio
async def test_regression_detected() -> None:
    database = Database(StorageConfig(db_path=":memory:"))
    await database.connect()
    await database.run_migrations()
    repo = EvalRunRepository(database)

    latest_id = await _insert_values(repo, [0.9, 0.88, 0.92, 0.91, 0.89, 0.1])
    report = await RegressionDetector(repo).check_regression("t", latest_id, baseline_window=5)
    assert report.regressed is True

    await database.close()


@pytest.mark.asyncio
async def test_no_regression() -> None:
    database = Database(StorageConfig(db_path=":memory:"))
    await database.connect()
    await database.run_migrations()
    repo = EvalRunRepository(database)

    latest_id = await _insert_values(repo, [0.8, 0.82, 0.79, 0.81, 0.8, 0.805])
    report = await RegressionDetector(repo).check_regression("t", latest_id, baseline_window=5)
    assert report.regressed is False

    await database.close()


@pytest.mark.asyncio
async def test_median_not_mean() -> None:
    database = Database(StorageConfig(db_path=":memory:"))
    await database.connect()
    await database.run_migrations()
    repo = EvalRunRepository(database)

    latest_id = await _insert_values(repo, [0.9, 0.9, 0.9, 0.1, 0.9, 0.2])
    report = await RegressionDetector(repo).check_regression("t", latest_id, baseline_window=5)
    assert report.baseline_median == 0.9

    await database.close()
