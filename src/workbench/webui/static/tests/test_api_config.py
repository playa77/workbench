"""Tests for workbench.api.routes.config."""

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench.api.routes.config import router, get_config
from workbench.core.auth import get_current_user
from workbench.core.models import User


def test_get_config_returns_theme_and_username():
    mock_user = MagicMock(spec=User)
    mock_user.username = "testuser"

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: mock_user

    client = TestClient(app)
    response = client.get("/config")

    assert response.status_code == 200
    assert response.json() == {"theme": "dark", "username": "testuser"}
