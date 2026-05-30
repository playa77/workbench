from fastapi.testclient import TestClient


def test_websocket_connect(client: TestClient) -> None:
    session_id = client.post("/api/v1/sessions", json={"mode": "chat"}).json()["data"]["id"]
    with client.websocket_connect(f"/api/v1/sessions/{session_id}/stream") as websocket:
        assert websocket is not None


def test_websocket_message_stream(client: TestClient) -> None:
    session_id = client.post("/api/v1/sessions", json={"mode": "chat"}).json()["data"]["id"]
    with client.websocket_connect(f"/api/v1/sessions/{session_id}/stream") as websocket:
        websocket.send_json({"type": "message", "content": "hello"})
        first = websocket.receive_json()
        done = websocket.receive_json()
    assert first["type"] == "text"
    assert done["type"] == "done"


def test_websocket_done_signal(client: TestClient) -> None:
    session_id = client.post("/api/v1/sessions", json={"mode": "chat"}).json()["data"]["id"]
    with client.websocket_connect(f"/api/v1/sessions/{session_id}/stream") as websocket:
        websocket.send_json({"type": "message", "content": "hello"})
        while True:
            event = websocket.receive_json()
            if event["type"] == "done":
                break
    assert event["type"] == "done"


def test_websocket_invalid_session(client: TestClient) -> None:
    with client.websocket_connect("/api/v1/sessions/not-real/stream") as websocket:
        event = websocket.receive_json()
        assert event["type"] == "error"
        assert event["error_code"] == "session_not_found"
