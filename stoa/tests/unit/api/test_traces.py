from fastapi.testclient import TestClient


def test_get_trace(client: TestClient) -> None:
    session_id = client.post("/api/v1/sessions", json={"mode": "chat"}).json()["data"]["id"]
    sent = client.post(f"/api/v1/sessions/{session_id}/messages", json={"content": "hello"}).json()
    trace_id = sent["data"]["trace_id"]

    response = client.get(f"/api/v1/traces/{trace_id}")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_get_trace_summary(client: TestClient) -> None:
    session_id = client.post("/api/v1/sessions", json={"mode": "chat"}).json()["data"]["id"]
    sent = client.post(f"/api/v1/sessions/{session_id}/messages", json={"content": "hello"}).json()
    trace_id = sent["data"]["trace_id"]

    response = client.get(f"/api/v1/traces/{trace_id}/summary")
    assert response.status_code == 200
    assert response.json()["data"]["trace_id"] == trace_id
