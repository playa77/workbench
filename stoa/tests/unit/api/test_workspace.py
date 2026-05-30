from pathlib import Path


def test_workspace_list_endpoint(client, tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    services = client.app.state.services
    services.config.workspace.allowed_paths = [str(tmp_path)]
    services.config.workspace.sandbox_mode = "strict"

    response = client.post("/api/v1/workspace/list", json={"path": str(tmp_path)})
    assert response.status_code == 200
    assert response.json()["data"]["files"]


def test_workspace_read_endpoint(client, tmp_path: Path) -> None:
    path = tmp_path / "r.txt"
    path.write_text("hello", encoding="utf-8")
    services = client.app.state.services
    services.config.workspace.allowed_paths = [str(tmp_path)]
    services.config.workspace.sandbox_mode = "strict"

    response = client.post("/api/v1/workspace/read", json={"path": str(path)})
    assert response.status_code == 200
    assert response.json()["data"]["file"]["content"] == "hello"


def test_workspace_write_endpoint(client, tmp_path: Path) -> None:
    services = client.app.state.services
    services.config.workspace.allowed_paths = [str(tmp_path)]
    services.config.workspace.sandbox_mode = "strict"
    services.config.workspace.confirm_writes = False

    path = tmp_path / "w.txt"
    response = client.post(
        "/api/v1/workspace/write",
        json={"path": str(path), "content": "world"},
    )
    assert response.status_code == 200
    assert path.read_text(encoding="utf-8") == "world"


def test_workspace_patch_and_apply_endpoint(client, tmp_path: Path) -> None:
    services = client.app.state.services
    services.config.workspace.allowed_paths = [str(tmp_path)]
    services.config.workspace.sandbox_mode = "strict"
    services.config.workspace.confirm_writes = False

    path = tmp_path / "p.txt"
    path.write_text("old", encoding="utf-8")
    create = client.post(
        "/api/v1/workspace/patch",
        json={"path": str(path), "replacement_text": "new", "description": "update"},
    )
    patch_id = create.json()["data"]["patch_id"]
    apply = client.post(f"/api/v1/workspace/patch/{patch_id}/apply")
    assert apply.status_code == 200
    assert path.read_text(encoding="utf-8") == "new"


def test_workspace_execute_endpoint(client, tmp_path: Path) -> None:
    services = client.app.state.services
    services.config.workspace.allowed_paths = [str(tmp_path)]
    services.config.workspace.sandbox_mode = "strict"
    services.config.workspace.confirm_executions = False

    response = client.post("/api/v1/workspace/execute", json={"command": "echo hello"})
    assert response.status_code == 200
    assert "hello" in response.json()["data"]["result"]["stdout"]
