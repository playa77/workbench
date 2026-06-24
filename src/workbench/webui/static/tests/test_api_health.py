"""Tests for workbench.api.routes.health."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench.api.routes.health import router


def test_health_returns_ok():
    app = FastAPI()
    app.include_router(router)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
