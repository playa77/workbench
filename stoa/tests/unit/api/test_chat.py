from fastapi.testclient import TestClient


def test_send_message(client: TestClient) -> None:
    session_id = client.post("/api/v1/sessions", json={"mode": "chat"}).json()["data"]["id"]
    response = client.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={"content": "hello"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["content"] == "Mock"


def test_get_message_history(client: TestClient) -> None:
    session_id = client.post("/api/v1/sessions", json={"mode": "chat"}).json()["data"]["id"]
    client.post(f"/api/v1/sessions/{session_id}/messages", json={"content": "first"})
    client.post(f"/api/v1/sessions/{session_id}/messages", json={"content": "second"})

    response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert response.status_code == 200
    messages = response.json()["data"]
    assert [message["sequence_num"] for message in messages] == [1, 2, 3, 4]
