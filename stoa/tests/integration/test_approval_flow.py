import threading
import time

import anyio
from pathlib import Path

from fastapi.testclient import TestClient


def _start_write(client: TestClient, path: Path, body: dict[str, object]) -> dict[str, object]:
    output: dict[str, object] = {}

    def runner() -> None:
        output["response"] = client.post(
            "/api/v1/workspace/write",
            json={"path": str(path), "content": "hello", **body},
        )

    thread = threading.Thread(target=runner)
    thread.start()
    output["thread"] = thread
    return output


def _wait_pending(client: TestClient) -> dict[str, object]:
    for _ in range(100):
        pending = client.get("/api/v1/approvals/pending").json()["data"]
        if pending:
            return pending[0]
        time.sleep(0.02)
    raise AssertionError("pending approval not found")


def test_full_approval_flow(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "approved.txt"
    started = _start_write(client, target, {"session_id": "s-approve", "trace_id": "t-approve"})
    pending = _wait_pending(client)
    assert pending["action"] == "workspace.write_file"

    decide = client.post(f"/api/v1/approvals/{pending['id']}", json={"approved": True})
    assert decide.status_code == 200

    started["thread"].join(timeout=5)
    response = started["response"]
    assert response.status_code == 200
    assert target.read_text(encoding="utf-8") == "hello"


def test_deny_cancels_operation(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "denied.txt"
    started = _start_write(client, target, {"session_id": "s-deny", "trace_id": "t-deny"})
    pending = _wait_pending(client)

    decide = client.post(
        f"/api/v1/approvals/{pending['id']}", json={"approved": False, "reason": "no"}
    )
    assert decide.status_code == 200

    started["thread"].join(timeout=5)
    response = started["response"]
    assert response.status_code == 500
    assert not target.exists()


def test_approval_timeout(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "timeout.txt"
    started = _start_write(client, target, {"session_id": "s-timeout", "trace_id": "t-timeout"})
    pending = _wait_pending(client)

    conn = client.app.state.services.database.connection()
    anyio.from_thread.run(conn.execute, "UPDATE approvals SET timeout_seconds = 0 WHERE id = ?", (pending["id"],))
    anyio.from_thread.run(conn.commit)

    started["thread"].join(timeout=5)
    response = started["response"]
    assert response.status_code == 500
    assert not target.exists()
