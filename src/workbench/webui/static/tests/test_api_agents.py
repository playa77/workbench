"""Tests for workbench.api.routes.agents."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench.api.routes.agents import router
from workbench.core.agents import AgentBase, get_registry
from workbench.core.auth import get_current_user
from workbench.core.db import get_session as get_db_session


class _TestAgent(AgentBase):
    name = "test_api_agent"
    display_name = "Test Agent"
    description = "A test agent used in API tests"


class _SettingsAgent(AgentBase):
    name = "test_settings_agent"
    display_name = "Settings Agent"
    description = "An agent with custom settings schema"

    def get_settings_schema(self):
        return {"type": "object", "properties": {"temperature": {"type": "number"}}}

    def get_default_settings(self):
        return {"temperature": 0.7}


# Register agents once for the module so tests share them.
# Using unique names avoids conflicts with other test modules.
registry = get_registry()
registry.register(_TestAgent())
registry.register(_SettingsAgent())


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid4()
    return user


@pytest.fixture
def override_get_session(db_session):
    async def _override():
        yield db_session
    return _override


@pytest.fixture
def client(mock_user, override_get_session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db_session] = override_get_session
    return TestClient(app)


def test_list_agents_empty_registry(client):
    """When no agents match (should still have registered ones), returns list."""
    response = client.get("/agents")
    assert response.status_code == 200
    data = response.json()
    # At minimum our two test agents should be present
    names = {a["name"] for a in data}
    assert "test_api_agent" in names
    assert "test_settings_agent" in names


def test_list_agents_with_registered_agent(client):
    """Verify a registered agent appears in the listing."""
    response = client.get("/agents")
    assert response.status_code == 200
    agents = {a["name"]: a for a in response.json()}
    agent = agents.get("test_api_agent")
    assert agent is not None
    assert agent["display_name"] == "Test Agent"
    assert agent["description"] == "A test agent used in API tests"


def test_get_agent_settings_found(client):
    """Get settings for a registered agent returns agent config with schema."""
    response = client.get("/agents/test_settings_agent/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["agent_name"] == "test_settings_agent"
    assert data["enabled"] is True
    assert data["settings_schema"] == {
        "type": "object", "properties": {"temperature": {"type": "number"}}
    }
    assert data["current_settings"] == {"temperature": 0.7}


def test_get_agent_settings_not_found(client):
    """GET settings for an unknown agent returns 404."""
    response = client.get("/agents/nonexistent_agent/settings")
    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found"


@pytest.mark.asyncio
async def test_update_agent_settings_enable(db_session, mock_user, override_get_session):
    """PUT to enable an agent succeeds."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db_session] = override_get_session
    client = TestClient(app)

    response = client.put("/agents/test_api_agent/settings", json={"enabled": True})
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True


@pytest.mark.asyncio
async def test_update_agent_settings_disable(db_session, mock_user, override_get_session):
    """PUT to disable an agent succeeds."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db_session] = override_get_session
    client = TestClient(app)

    response = client.put("/agents/test_api_agent/settings", json={"enabled": False})
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False


def test_update_agent_settings_not_found(client):
    """PUT settings for an unknown agent returns 404."""
    response = client.put(
        "/agents/nonexistent_agent/settings",
        json={"enabled": True},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found"


# ─── Direct handler coverage tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_agents_direct(db_session, mock_user):
    """Directly call list_agents handler for coverage."""
    from workbench.api.routes.agents import list_agents

    result = await list_agents(mock_user, db_session)
    assert isinstance(result, list)
    names = {a.name for a in result}
    assert "test_api_agent" in names


@pytest.mark.asyncio
async def test_get_agent_settings_direct(db_session, mock_user):
    """Directly call get_agent_settings handler for coverage."""
    from workbench.api.routes.agents import get_agent_settings

    result = await get_agent_settings("test_settings_agent", mock_user, db_session)
    assert result["agent_name"] == "test_settings_agent"
    assert result["enabled"] is True
    assert result["settings_schema"] is not None

    # Not found case
    with pytest.raises(Exception):
        await get_agent_settings("nonexistent", mock_user, db_session)


@pytest.mark.asyncio
async def test_update_agent_settings_direct(db_session, mock_user):
    """Directly call update_agent_settings handler for coverage."""
    from workbench.api.routes.agents import update_agent_settings, AgentSettingsUpdate

    body = AgentSettingsUpdate(enabled=True, settings={"key": "val"})
    result = await update_agent_settings("test_api_agent", body, mock_user, db_session)
    assert result["enabled"] is True

    body = AgentSettingsUpdate(enabled=False, settings=None)
    result = await update_agent_settings("test_api_agent", body, mock_user, db_session)
    assert result["enabled"] is False

    # Not found
    body = AgentSettingsUpdate(enabled=True)
    with pytest.raises(Exception):
        await update_agent_settings("nonexistent", body, mock_user, db_session)
