from fastapi.testclient import TestClient

from caw.api.app import create_app
from caw.core.config import CAWConfig


def test_health_endpoint() -> None:
    app = create_app(CAWConfig())
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_unknown_route_404() -> None:
    app = create_app(CAWConfig())
    with TestClient(app) as client:
        response = client.get("/nonexistent")
    assert response.status_code == 404


def test_cors_headers() -> None:
    config = CAWConfig.model_validate({"api": {"cors_origins": ["http://example.com"]}})
    app = create_app(config)
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://example.com"
