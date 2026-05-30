from fastapi.testclient import TestClient


def test_evaluation_journey(client: TestClient) -> None:
    run1 = client.post("/api/v1/eval/run", json={"task_id": "research.sample"})
    assert run1.status_code == 200
    run1_id = run1.json()["data"]["run_id"]

    run2 = client.post("/api/v1/eval/run", json={"task_id": "research.sample"})
    assert run2.status_code == 200
    run2_id = run2.json()["data"]["run_id"]

    compare = client.post("/api/v1/eval/compare", json={"run_ids": [run1_id, run2_id]})
    assert compare.status_code == 200

    regression = client.post(
        "/api/v1/eval/regression",
        json={"task_id": "research.sample", "latest_run_id": run2_id, "baseline_window": 5},
    )
    assert regression.status_code == 200

    runs = client.get("/api/v1/eval/runs", params={"task_id": "research.sample"})
    assert runs.status_code == 200
    assert len(runs.json()["data"]) >= 2
