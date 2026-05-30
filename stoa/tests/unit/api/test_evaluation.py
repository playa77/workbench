import asyncio

from caw.models import EvalRun
from caw.storage.repository import EvalRunRepository


def test_eval_run_endpoint(client) -> None:
    services = client.app.state.services
    services.config.evaluation.tasks_dir = "tests/fixtures/tasks"
    response = client.post("/api/v1/eval/run", json={"task_id": "research.sample"})
    assert response.status_code == 200
    assert response.json()["data"]["task_id"] == "research.sample"


def test_eval_runs_endpoint(client) -> None:
    services = client.app.state.services
    repo = EvalRunRepository(services.database)
    asyncio.run(repo.create(EvalRun(task_id="abc", provider="p", model="m", status="completed")))

    response = client.get("/api/v1/eval/runs", params={"task_id": "abc"})
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


def test_eval_run_detail_endpoint(client) -> None:
    services = client.app.state.services
    repo = EvalRunRepository(services.database)
    run = asyncio.run(
        repo.create(EvalRun(task_id="abc", provider="p", model="m", status="completed"))
    )

    response = client.get(f"/api/v1/eval/runs/{run.id}")
    assert response.status_code == 200
    assert response.json()["data"]["id"] == run.id


def test_eval_compare_endpoint(client) -> None:
    services = client.app.state.services
    repo = EvalRunRepository(services.database)
    run_a = asyncio.run(
        repo.create(
            EvalRun(
                task_id="abc",
                provider="p",
                model="m",
                status="completed",
                scores={"composite": 0.4},
            )
        )
    )
    run_b = asyncio.run(
        repo.create(
            EvalRun(
                task_id="abc",
                provider="p",
                model="m",
                status="completed",
                scores={"composite": 0.8},
            )
        )
    )

    response = client.post("/api/v1/eval/compare", json={"run_ids": [run_a.id, run_b.id]})
    assert response.status_code == 200
    assert response.json()["data"]["matrix"][run_a.id]["composite"] == 0.4


def test_eval_regression_endpoint(client) -> None:
    services = client.app.state.services
    repo = EvalRunRepository(services.database)
    for value in [0.9, 0.88, 0.92, 0.9, 0.89, 0.2]:
        run = asyncio.run(
            repo.create(
                EvalRun(
                    task_id="abc",
                    provider="p",
                    model="m",
                    status="completed",
                    scores={"composite": value},
                )
            )
        )

    response = client.post(
        "/api/v1/eval/regression",
        json={"task_id": "abc", "latest_run_id": run.id, "baseline_window": 5},
    )
    assert response.status_code == 200
    assert response.json()["data"]["latest_run_id"] == run.id
