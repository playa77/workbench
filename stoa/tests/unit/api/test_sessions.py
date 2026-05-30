from fastapi.testclient import TestClient


def test_create_session(client: TestClient) -> None:
    response = client.post("/api/v1/sessions", json={"mode": "chat"})
    assert response.status_code == 201
    assert response.json()["data"]["mode"] == "chat"


def test_get_session(client: TestClient) -> None:
    created = client.post("/api/v1/sessions", json={"mode": "chat"}).json()["data"]
    response = client.get(f"/api/v1/sessions/{created['id']}")
    assert response.status_code == 200
    assert response.json()["data"]["id"] == created["id"]


def test_get_session_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/sessions/not-real")
    assert response.status_code == 400
    assert response.json()["error_code"] == "session_not_found"


def test_list_sessions(client: TestClient) -> None:
    for _ in range(3):
        client.post("/api/v1/sessions", json={"mode": "chat"})
    response = client.get("/api/v1/sessions?limit=10")
    assert response.status_code == 200
    assert len(response.json()["data"]) >= 3
