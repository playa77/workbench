from pathlib import Path

from caw.models import SessionMode


def test_research_ingest_endpoint(client) -> None:
    response = client.post(
        "/api/v1/sessions",
        json={"mode": SessionMode.RESEARCH.value},
    )
    session_id = response.json()["data"]["id"]
    ingest = client.post(
        "/api/v1/research/ingest",
        json={"session_id": session_id, "path": str(Path("tests/fixtures/research/sample.txt"))},
    )
    assert ingest.status_code == 200
    assert ingest.json()["data"]["source_id"]


def test_research_retrieve_endpoint(client) -> None:
    session_id = client.post("/api/v1/sessions", json={"mode": "research"}).json()["data"]["id"]
    client.post(
        "/api/v1/research/ingest",
        json={"session_id": session_id, "path": "tests/fixtures/research/sample.txt"},
    )
    response = client.post(
        "/api/v1/research/retrieve",
        json={"session_id": session_id, "query": "sample"},
    )
    assert response.status_code == 200
    assert response.json()["data"]


def test_research_synthesize_endpoint(client) -> None:
    session_id = client.post("/api/v1/sessions", json={"mode": "research"}).json()["data"]["id"]
    client.post(
        "/api/v1/research/ingest",
        json={"session_id": session_id, "path": "tests/fixtures/research/sample.txt"},
    )
    response = client.post(
        "/api/v1/research/synthesize",
        json={"session_id": session_id, "query": "sample"},
    )
    assert response.status_code == 200
    assert "claims" in response.json()["data"]


def test_research_export_endpoint(client) -> None:
    session_id = client.post("/api/v1/sessions", json={"mode": "research"}).json()["data"]["id"]
    client.post(
        "/api/v1/research/ingest",
        json={"session_id": session_id, "path": "tests/fixtures/research/sample.txt"},
    )
    response = client.post(
        "/api/v1/research/export",
        json={"session_id": session_id, "query": "sample", "format": "json"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["artifact_id"]
