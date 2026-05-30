from pathlib import Path

from fastapi.testclient import TestClient


def test_research_journey(client: TestClient) -> None:
    session = client.post("/api/v1/sessions", json={"mode": "research"}).json()["data"]
    session_id = session["id"]

    ingest = client.post(
        "/api/v1/research/ingest",
        json={"session_id": session_id, "path": str(Path("tests/fixtures/research/sample.txt"))},
    )
    assert ingest.status_code == 200

    retrieve = client.post(
        "/api/v1/research/retrieve", json={"session_id": session_id, "query": "sample"}
    )
    assert retrieve.status_code == 200
    assert retrieve.json()["data"]

    synth = client.post(
        "/api/v1/research/synthesize", json={"session_id": session_id, "query": "sample"}
    )
    assert synth.status_code == 200

    export = client.post(
        "/api/v1/research/export", json={"session_id": session_id, "query": "sample"}
    )
    assert export.status_code == 200
    assert export.json()["data"]["artifact_id"]

    trace_id = synth.json()["data"]["trace_id"]
    trace = client.get(f"/api/v1/traces/{trace_id}")
    assert trace.status_code == 200
    event_types = {event["event_type"] for event in trace.json()["data"]}
    assert {"synthesis:started", "synthesis:completed"} <= event_types
