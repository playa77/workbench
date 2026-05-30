from fastapi.testclient import TestClient


def test_list_skills(client: TestClient) -> None:
    response = client.get("/api/v1/skills")
    assert response.status_code == 200
    assert "data" in response.json()


def test_get_skill(client: TestClient) -> None:
    response = client.get("/api/v1/skills/unknown")
    assert response.status_code == 200
    assert response.json()["status"] == "error"


def test_list_packs(client: TestClient) -> None:
    response = client.get("/api/v1/skills/packs")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_list_providers(client: TestClient) -> None:
    response = client.get("/api/v1/providers")
    assert response.status_code == 200
    assert "primary" in response.json()["data"]


def test_provider_health(client: TestClient) -> None:
    response = client.get("/api/v1/providers/primary/health")
    assert response.status_code == 200
    assert response.json()["data"]["available"] is True
