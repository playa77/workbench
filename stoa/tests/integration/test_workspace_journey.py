import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient


def test_workspace_journey(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "journey.txt"

    list_response = client.post(
        "/api/v1/workspace/list", json={"path": str(tmp_path), "session_id": "w1", "trace_id": "w-list"}
    )
    assert list_response.status_code == 200

    read_response = client.post(
        "/api/v1/workspace/read", json={"path": str(tmp_path), "session_id": "w1", "trace_id": "w-read"}
    )
    assert read_response.status_code == 200

    response_holder: dict[str, object] = {}

    def do_write() -> None:
        response_holder["response"] = client.post(
            "/api/v1/workspace/write",
            json={
                "path": str(target),
                "content": "journey",
                "session_id": "w1",
                "trace_id": "w-write",
            },
        )

    thread = threading.Thread(target=do_write)
    thread.start()

    pending: list[dict[str, object]] = []
    for _ in range(100):
        pending = client.get("/api/v1/approvals/pending").json()["data"]
        if pending:
            break
        time.sleep(0.02)
    assert pending

    decision = client.post(f"/api/v1/approvals/{pending[0]['id']}", json={"approved": True})
    assert decision.status_code == 200

    thread.join(timeout=5)
    write_response = response_holder["response"]
    assert write_response.status_code == 200
    assert target.read_text(encoding="utf-8") == "journey"
