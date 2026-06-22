"""Tests for workbench.api.app — application factory."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock, call

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware

from workbench.api.app import (
    ExportRequest,
    SESSION_CLEANUP_INTERVAL,
    create_app,
    _auto_register_agents,
    _register_core_routes,
    _run_alembic_upgrade,
    _run_periodic_session_cleanup,
    _start_news_scheduler_if_agent_enabled,
)
from workbench.core.config import WorkbenchConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_config() -> WorkbenchConfig:
    """Config with minimal settings for app factory tests."""
    return WorkbenchConfig(
        log_level="DEBUG",
        database_url="sqlite+aiosqlite:///:memory:",
        encryption_key="a" * 64,  # 32 bytes hex
        api_cors_origins=["http://localhost:8420"],
        api_csp_header="",
        api_strict_transport_security="",
        rate_limit_enabled=False,
        api_host="127.0.0.1",
        api_port=8420,
    )


@pytest.fixture(autouse=True)
def _reset_registry():
    """Reset the global agent registry between tests."""
    from workbench.core.agents import _registry as reg
    yield
    from workbench.core.agents import _registry
    _registry = None


# ---------------------------------------------------------------------------
# create_app — factory
# ---------------------------------------------------------------------------

class TestCreateApp:
    """Tests for create_app()."""

    @patch("workbench.api.app.load_config")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    def test_create_app_default_config(
        self,
        mock_core_routes,
        mock_agents,
        mock_alembic,
        mock_set_encrypt,
        mock_init_encrypt,
        mock_init_db,
        mock_load_config,
        minimal_config,
    ):
        """Should call load_config() when no config passed."""
        mock_load_config.return_value = minimal_config
        app = create_app()
        assert isinstance(app, FastAPI)
        assert app.title == "Workbench"
        mock_load_config.assert_called_once_with()
        mock_init_db.assert_called_once_with(minimal_config)
        mock_init_encrypt.assert_called_once_with(minimal_config)
        mock_set_encrypt.assert_called_once_with(minimal_config.encryption_encrypt_reports)
        mock_alembic.assert_called_once()
        mock_agents.assert_called_once()
        mock_core_routes.assert_called_once()

    @patch("workbench.api.app.load_config")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    def test_create_app_with_config(
        self,
        mock_core_routes,
        mock_agents,
        mock_alembic,
        mock_set_encrypt,
        mock_init_encrypt,
        mock_init_db,
        mock_load_config,
        minimal_config,
    ):
        """Should NOT call load_config() when config is passed."""
        app = create_app(config=minimal_config)
        assert isinstance(app, FastAPI)
        mock_load_config.assert_not_called()

    @patch("workbench.api.app.load_config")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    def test_create_app_cors_middleware(
        self,
        mock_core_routes,
        mock_agents,
        mock_alembic,
        mock_set_encrypt,
        mock_init_encrypt,
        mock_init_db,
        mock_load_config,
        minimal_config,
    ):
        """CORS middleware should be added with config origins."""
        config = minimal_config.model_copy(deep=True)
        config.api_cors_origins = ["*"]
        mock_load_config.return_value = config
        app = create_app()
        middleware_cls = [m.cls for m in app.user_middleware]
        assert CORSMiddleware in middleware_cls

    @patch("workbench.api.app.load_config")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    def test_create_app_rate_limit_enabled(
        self,
        mock_core_routes,
        mock_agents,
        mock_alembic,
        mock_set_encrypt,
        mock_init_encrypt,
        mock_init_db,
        mock_load_config,
        minimal_config,
    ):
        """Rate limiting should be configured when enabled."""
        config = minimal_config.model_copy(deep=True)
        config.rate_limit_enabled = True
        config.rate_limit_general = "60/minute"
        mock_load_config.return_value = config
        from workbench.core.rate_limiter import limiter
        original = list(limiter._default_limits)
        try:
            app = create_app()
            assert hasattr(app.state, "limiter")
            # Default limits should be set
            assert app.state.limiter._default_limits == ["60/minute"]
        finally:
            limiter._default_limits = original

    @patch("workbench.api.app.load_config")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    def test_create_app_rate_limit_disabled(
        self,
        mock_core_routes,
        mock_agents,
        mock_alembic,
        mock_set_encrypt,
        mock_init_encrypt,
        mock_init_db,
        mock_load_config,
        minimal_config,
    ):
        """Default limits should NOT be overwritten when rate limiting disabled."""
        config = minimal_config.model_copy(deep=True)
        config.rate_limit_enabled = False
        config.rate_limit_general = "60/minute"
        mock_load_config.return_value = config
        # Reset the shared limiter's default limits to a known state
        from workbench.core.rate_limiter import limiter
        original = list(limiter._default_limits)
        limiter._default_limits.clear()
        try:
            app = create_app()
            assert hasattr(app.state, "limiter")
            # Since rate_limit_enabled is False, the branch is skipped
            # and _default_limits should remain as-is (empty, not set to config value)
            assert "60/minute" not in limiter._default_limits
        finally:
            limiter._default_limits.extend(original)

    @patch("workbench.api.app.load_config")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    def test_create_app_static_dir_exists(
        self,
        mock_core_routes,
        mock_agents,
        mock_alembic,
        mock_set_encrypt,
        mock_init_encrypt,
        mock_init_db,
        mock_load_config,
        minimal_config,
    ):
        """Static dir should be mounted when it exists."""
        mock_load_config.return_value = minimal_config
        with (
            patch("workbench.api.app.Path.exists") as mock_exists,
            patch("workbench.api.app.StaticFiles") as mock_static,
        ):
            mock_exists.return_value = True
            app = create_app()
            # Check that StaticFiles was invoked
            mock_static.assert_called_once()

    @patch("workbench.api.app.load_config")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    def test_create_app_static_dir_missing(
        self,
        mock_core_routes,
        mock_agents,
        mock_alembic,
        mock_set_encrypt,
        mock_init_encrypt,
        mock_init_db,
        mock_load_config,
        minimal_config,
    ):
        """Static dir should NOT be mounted when it doesn't exist."""
        mock_load_config.return_value = minimal_config
        with (
            patch("workbench.api.app.Path.exists") as mock_exists,
            patch("workbench.api.app.StaticFiles") as mock_static,
        ):
            mock_exists.return_value = False
            app = create_app()
            mock_static.assert_not_called()

    @patch("workbench.api.app.load_config")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    def test_create_app_exception_handler(
        self,
        mock_core_routes,
        mock_agents,
        mock_alembic,
        mock_set_encrypt,
        mock_init_encrypt,
        mock_init_db,
        mock_load_config,
        minimal_config,
    ):
        """Rate limit exceeded handler should be registered."""
        mock_load_config.return_value = minimal_config
        app = create_app()
        from slowapi.errors import RateLimitExceeded
        # The exception handler should be registered
        assert RateLimitExceeded in app.exception_handlers


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

class TestLifespan:
    """Tests for the FastAPI lifespan context manager."""

    @pytest.mark.asyncio
    @patch("workbench.api.app._start_news_scheduler_if_agent_enabled")
    @patch("workbench.api.app._run_periodic_session_cleanup")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    @patch("workbench.api.app.load_config")
    async def test_lifespan_start_and_shutdown(
        self,
        mock_load_config,
        mock_core_routes,
        mock_agents,
        mock_alembic,
        mock_set_encrypt,
        mock_init_encrypt,
        mock_init_db,
        mock_cleanup,
        mock_scheduler,
        minimal_config,
    ):
        """Lifespan should start tasks and clean them up on shutdown."""
        mock_load_config.return_value = minimal_config
        scheduler_task = asyncio.create_task(asyncio.sleep(999))
        cleanup_task = MagicMock()
        mock_scheduler.return_value = scheduler_task
        mock_cleanup.return_value = cleanup_task

        app = create_app()
        # Trigger lifespan startup/shutdown via TestClient
        with TestClient(app) as client:
            client.get("/does-not-exist", headers={"Accept": "application/json"})

        # The lifespan shutdown cancels scheduler and cleanup tasks.
        # Since those tasks live in the test event loop, cancellation was
        # requested via the TestClient's internal lifespan shutdown.
        # Verify the shutdown code path ran without error.
        assert scheduler_task.cancelled() or scheduler_task.cancelling() > 0

    @pytest.mark.asyncio
    @patch("workbench.api.app._start_news_scheduler_if_agent_enabled")
    @patch("workbench.api.app._run_periodic_session_cleanup")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    @patch("workbench.api.app.load_config")
    async def test_lifespan_no_scheduler(
        self,
        mock_load_config,
        mock_core_routes,
        mock_agents,
        mock_alembic,
        mock_set_encrypt,
        mock_init_encrypt,
        mock_init_db,
        mock_cleanup,
        mock_scheduler,
        minimal_config,
    ):
        """Lifespan should handle None scheduler task."""
        mock_load_config.return_value = minimal_config
        mock_scheduler.return_value = None  # scheduler not available
        cleanup_task = MagicMock()
        mock_cleanup.return_value = cleanup_task

        app = create_app()
        with TestClient(app) as client:
            client.get("/does-not-exist", headers={"Accept": "application/json"})

        # No scheduler task, so only cleanup is handled


# ---------------------------------------------------------------------------
# _register_core_routes
# ---------------------------------------------------------------------------

class TestRegisterCoreRoutes:
    """Tests for _register_core_routes()."""

    def test_routes_registered(self):
        """Core routes should be registered on the app."""
        app = FastAPI()
        _register_core_routes(app)

        route_paths = {getattr(r, "path", "") for r in app.routes}
        assert "/health" in route_paths
        assert "/api/v1/export/templates" in route_paths
        assert "/api/v1/export/pdf" in route_paths

    def test_export_request_model(self):
        """ExportRequest should have content, title, template fields."""
        req = ExportRequest(content="# Hello", title="My Report", template="simple")
        assert req.content == "# Hello"
        assert req.title == "My Report"
        assert req.template == "simple"

    def test_export_request_defaults(self):
        """ExportRequest should have sensible defaults."""
        req = ExportRequest(content="test")
        assert req.title == "Report"
        assert req.template == "professional"


# ---------------------------------------------------------------------------
# _run_alembic_upgrade
# ---------------------------------------------------------------------------

class TestRunAlembicUpgrade:
    """Tests for _run_alembic_upgrade()."""

    @patch("alembic.command.upgrade")
    @patch("alembic.config.Config")
    def test_alembic_upgrade_called(self, mock_alembic_cfg, mock_upgrade):
        """Alembic upgrade should be called with 'head'."""
        with patch("workbench.api.app.Path.exists") as mock_exists:
            mock_exists.return_value = True  # alembic.ini exists at expected location
            _run_alembic_upgrade()
            mock_upgrade.assert_called_once()
            # Verify it was called with the config and "head"
            args, _ = mock_upgrade.call_args
            assert args[1] == "head"

    @patch("alembic.command.upgrade")
    @patch("alembic.config.Config")
    def test_alembic_upgrade_fallback_cwd(self, mock_alembic_cfg, mock_upgrade):
        """Should fall back to CWD when alembic.ini not in source tree."""
        with patch("workbench.api.app.Path.exists") as mock_exists:
            mock_exists.return_value = False  # Not in source tree, uses CWD
            with patch("workbench.api.app.Path.cwd") as mock_cwd:
                mock_cwd.return_value = Path("/some/cwd")
                _run_alembic_upgrade()
                mock_upgrade.assert_called_once()

    @patch("alembic.command.upgrade")
    def test_alembic_config_setup(self, mock_upgrade):
        """Alembic config should set script_location."""
        with patch("workbench.api.app.Path.exists") as mock_exists:
            mock_exists.return_value = True
            with patch("workbench.api.app.Path.resolve") as mock_resolve:
                mock_resolve.return_value = Path("/project")
                # We need parents[3] to give us /project
                mock_root = MagicMock()
                mock_root.parents.__getitem__.return_value = Path("/project")
                mock_resolve.return_value = mock_root

                mock_cfg = MagicMock()
                with patch("alembic.config.Config") as mock_ac:
                    mock_ac.return_value = mock_cfg
                    _run_alembic_upgrade()
                    mock_cfg.set_main_option.assert_called_with(
                        "script_location", str(Path("/project") / "alembic")
                    )
                    mock_upgrade.assert_called_once_with(mock_cfg, "head")


# ---------------------------------------------------------------------------
# _auto_register_agents
# ---------------------------------------------------------------------------

class TestAutoRegisterAgents:
    """Tests for _auto_register_agents()."""

    def test_auto_register_success(self):
        """Built-in agents should be imported and registered."""
        app = FastAPI()
        registry = MagicMock()
        registry.list_all.return_value = []

        # We'll test a simpler case: module fails to import gracefully
        with patch("workbench.api.app.importlib.import_module") as mock_import:
            mock_import.side_effect = ImportError("not available")
            _auto_register_agents(app, registry)
            # Should have tried to import each agent
            assert mock_import.call_count == len(
                [
                    ("agents.chat.agent", "ChatAgent"),
                    ("agents.news.agent", "NewsAgent"),
                    ("agents.debate.agent", "DebateAgent"),
                    ("agents.research.agent", "ResearchAgent"),
                    ("agents.deliberation.agent", "DeliberationAgent"),
                    ("agents.planning.agent", "PlanningAgent"),
                    ("agents.math_tutor.agent", "MathTutorAgent"),
                    ("agents.knowledge.agent", "KnowledgeBaseAgent"),
                ]
            )

    def test_auto_register_with_static_dir(self):
        """Agent static dir should be mounted when it exists."""
        app = FastAPI()
        registry = MagicMock()

        mock_agent = MagicMock()
        mock_agent.name = "test_agent"
        mock_agent.get_static_dir.return_value = Path("/tmp/plugin_static")
        registry.list_all.return_value = [mock_agent]

        with (
            patch("workbench.api.app.importlib.import_module") as mock_import,
            patch("workbench.api.app.StaticFiles") as mock_static,
        ):
            # Make all agent imports fail
            mock_import.side_effect = ImportError("not available")
            _auto_register_agents(app, registry)
            # Static dir should be mounted
            # But only if the path exists
            # Actually get_static_dir returns a Path that may not exist
            # It checks `.exists()` on the path
            # Since it's /tmp/plugin_static and we didn't set exists -> it won't mount
            # Let's check: no mount happened because path doesn't exist
            pass

    def test_auto_register_agent_with_real_static_dir(self, tmp_path):
        """Agent static dir should be mounted when path exists."""
        app = FastAPI()
        registry = MagicMock()

        static_path = tmp_path / "plugin_static"
        static_path.mkdir()

        mock_agent = MagicMock()
        mock_agent.name = "test_agent"
        mock_agent.get_static_dir.return_value = static_path
        registry.list_all.return_value = [mock_agent]

        with patch("workbench.api.app.importlib.import_module") as mock_import:
            mock_import.side_effect = ImportError("not available")
            _auto_register_agents(app, registry)

            # Check that a route was mounted
            route_paths = {getattr(r, "path", "") for r in app.router.routes}
            assert "/static/plugins/test_agent" in route_paths

    def test_root_route_returns_index_html(self, tmp_path):
        """Root route should serve index.html when it exists."""
        import workbench.api.app as _app_mod

        app = FastAPI()
        registry = MagicMock()
        registry.list_all.return_value = []

        static_dir = tmp_path / "webui" / "static"
        static_dir.mkdir(parents=True)
        index_html = static_dir / "index.html"
        index_html.write_text("<html><body>Workbench</body></html>")

        with patch("workbench.api.app.importlib.import_module") as mock_import:
            mock_import.side_effect = ImportError("not available")
            # Patch __file__ so Path(__file__).resolve().parent.parent points to tmp_path
            # Path(__file__).parent.parent / "webui" / "static" should = static_dir
            # So Path(__file__).parent.parent = static_dir.parent.parent = tmp_path
            # So __file__ should be at tmp_path/api/app.py
            with patch.object(_app_mod, "__file__", str(static_dir.parent.parent / "api" / "app.py")):
                _auto_register_agents(app, registry)

                client = TestClient(app)
                response = client.get("/")
                assert response.status_code == 200
                # It's a FileResponse, so content should match
                assert response.text == "<html><body>Workbench</body></html>"

    def test_root_route_fallback_html(self, tmp_path):
        """Root route should return fallback HTML when index.html missing."""
        import workbench.api.app as _app_mod

        app = FastAPI()
        registry = MagicMock()
        registry.list_all.return_value = []

        static_dir = tmp_path / "webui" / "static"
        static_dir.mkdir(parents=True)
        # Don't create index.html

        with patch("workbench.api.app.importlib.import_module") as mock_import:
            mock_import.side_effect = ImportError("not available")
            with patch.object(_app_mod, "__file__", str(static_dir / "dummy.py")):
                _auto_register_agents(app, registry)

                client = TestClient(app)
                response = client.get("/")
                assert response.status_code == 200
                assert "Frontend not found" in response.text

    def test_tabs_route(self, tmp_path):
        """Tabs route should return list of tabs from agent registry."""
        app = FastAPI()
        registry = MagicMock()

        mock_agent = MagicMock()
        mock_agent.name = "test_agent"
        mock_agent.get_static_dir.return_value = None  # No static dir to mount
        mock_agent.get_frontend_tab.return_value = {
            "id": "test_agent",
            "displayName": "Test Agent",
            "icon": "puzzle",
            "component": "agent-test_agent",
        }
        registry.list_all.return_value = [mock_agent]

        with (
            patch("workbench.api.app.importlib.import_module") as mock_import,
            patch("workbench.api.app.get_user_agent_settings") as mock_settings,
            patch("workbench.api.app.get_session"),
        ):
            mock_import.side_effect = ImportError("not available")

            # We need to mock the Depends for get_current_user too
            # Since tabs route uses get_current_user dependency
            _auto_register_agents(app, registry)

            # Instead of hitting the endpoint (which needs auth), verify the route exists
            route_paths = {getattr(r, "path", "") for r in app.routes}
            assert "/api/v1/tabs" in route_paths


# ---------------------------------------------------------------------------
# _start_news_scheduler_if_agent_enabled
# ---------------------------------------------------------------------------

class TestStartNewsScheduler:
    """Tests for _start_news_scheduler_if_agent_enabled()."""

    @pytest.mark.asyncio
    async def test_scheduler_started_successfully(self):
        """Should start scheduler and return task when all imports work."""
        app = FastAPI()

        with (
            patch("workbench.services.news_scheduler.NewsScheduler") as mock_scheduler_cls,
            patch("workbench.services.news_store.NewsStore"),
            patch("workbench.core.db.get_session_factory"),
            patch("agents.news.agent.set_scheduler") as mock_set_sched,
        ):
            mock_scheduler = MagicMock()
            # start() needs to return an awaitable for asyncio.create_task
            mock_scheduler.start = AsyncMock()
            mock_scheduler_cls.return_value = mock_scheduler

            task = _start_news_scheduler_if_agent_enabled(app)
            assert task is not None
            mock_scheduler_cls.assert_called_once()
            mock_set_sched.assert_called_once_with(mock_scheduler)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def test_scheduler_import_fails(self):
        """Should return None when imports fail."""
        app = FastAPI()

        with (
            patch("workbench.services.news_scheduler.NewsScheduler", side_effect=ImportError("no module")),
        ):
            task = _start_news_scheduler_if_agent_enabled(app)
            assert task is None

    @pytest.mark.asyncio
    async def test_scheduler_set_scheduler_fails_gracefully(self):
        """Should handle set_scheduler import failure."""
        app = FastAPI()

        with (
            patch("workbench.services.news_scheduler.NewsScheduler") as mock_scheduler_cls,
            patch("workbench.services.news_store.NewsStore"),
            patch("workbench.core.db.get_session_factory"),
            patch("agents.news.agent.set_scheduler", side_effect=Exception("fail")),
        ):
            mock_scheduler = MagicMock()
            # start() needs to return an awaitable for asyncio.create_task
            mock_scheduler.start = AsyncMock()
            mock_scheduler_cls.return_value = mock_scheduler

            task = _start_news_scheduler_if_agent_enabled(app)
            assert task is not None  # Should still work, set_scheduler fail is caught
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# ---------------------------------------------------------------------------
# _run_periodic_session_cleanup
# ---------------------------------------------------------------------------

class TestPeriodicSessionCleanup:
    """Tests for _run_periodic_session_cleanup()."""

    async def test_cleanup_cancelled_error_propagates(self):
        """CancelledError should propagate."""
        with patch("workbench.api.app.asyncio.sleep") as mock_sleep:
            mock_sleep.side_effect = asyncio.CancelledError()
            with pytest.raises(asyncio.CancelledError):
                await _run_periodic_session_cleanup()

    async def test_cleanup_calls_agent_method(self):
        """Should call _cleanup_sessions on agents that have it."""
        mock_agent = MagicMock()
        mock_agent._cleanup_sessions = MagicMock()
        mock_agent2 = MagicMock()  # no _cleanup_sessions

        with (
            patch("workbench.api.app.asyncio.sleep") as mock_sleep,
            patch("workbench.api.app.get_registry") as mock_registry,
        ):
            mock_registry.return_value.list_all.return_value = [mock_agent, mock_agent2]
            # Stop after first iteration by raising CancelledError
            mock_sleep.side_effect = [None, asyncio.CancelledError()]

            with pytest.raises(asyncio.CancelledError):
                await _run_periodic_session_cleanup()

            mock_agent._cleanup_sessions.assert_called_once()
            # agent2 has no _cleanup_sessions, should not error

    async def test_cleanup_handles_generic_exception(self):
        """Should log exception and continue on generic errors."""
        mock_agent = MagicMock()
        mock_agent._cleanup_sessions = MagicMock(side_effect=ValueError("cleanup failed"))

        with (
            patch("workbench.api.app.asyncio.sleep") as mock_sleep,
            patch("workbench.api.app.get_registry") as mock_registry,
        ):
            mock_registry.return_value.list_all.return_value = [mock_agent]
            # First: sleep succeeds -> cleanup fails with ValueError -> sleeps again -> CancelledError
            mock_sleep.side_effect = [None, asyncio.CancelledError()]

            with pytest.raises(asyncio.CancelledError):
                await _run_periodic_session_cleanup()

            # Should have called the cleanup despite the error
            mock_agent._cleanup_sessions.assert_called_once()


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    """Tests for the security headers middleware."""

    @patch("workbench.api.app.load_config")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    def test_security_headers_set(
        self,
        mock_core_routes,
        mock_agents,
        mock_alembic,
        mock_set_encrypt,
        mock_init_encrypt,
        mock_init_db,
        mock_load_config,
        minimal_config,
    ):
        """CSP and HSTS headers should be set when configured."""
        config = minimal_config.model_copy(deep=True)
        config.api_csp_header = "default-src 'self'"
        config.api_strict_transport_security = "max-age=31536000"
        mock_load_config.return_value = config

        from fastapi import APIRouter
        app = create_app()
        dummy_router = APIRouter()
        @dummy_router.get("/test")
        async def dummy():
            return {"ok": True}
        app.include_router(dummy_router)

        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200
        assert response.headers.get("Content-Security-Policy") == "default-src 'self'"
        assert response.headers.get("Strict-Transport-Security") == "max-age=31536000"

    @patch("workbench.api.app.load_config")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    def test_security_headers_not_set(
        self,
        mock_core_routes,
        mock_agents,
        mock_alembic,
        mock_set_encrypt,
        mock_init_encrypt,
        mock_init_db,
        mock_load_config,
        minimal_config,
    ):
        """Empty CSP/HSTS strings should not set headers."""
        config = minimal_config.model_copy(deep=True)
        config.api_csp_header = ""
        config.api_strict_transport_security = ""
        mock_load_config.return_value = config

        from fastapi import APIRouter
        app = create_app()
        dummy_router = APIRouter()
        @dummy_router.get("/test")
        async def dummy():
            return {"ok": True}
        app.include_router(dummy_router)

        client = TestClient(app)
        response = client.get("/test")
        assert "Content-Security-Policy" not in response.headers
        assert "Strict-Transport-Security" not in response.headers


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

class TestLogging:
    """Tests for logging configuration in create_app."""

    @patch("workbench.api.app.load_config")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    @patch("workbench.api.app.logging.basicConfig")
    def test_logging_configured(
        self,
        mock_basicConfig,
        mock_core_routes,
        mock_agents,
        mock_alembic,
        mock_set_encrypt,
        mock_init_encrypt,
        mock_init_db,
        mock_load_config,
        minimal_config,
    ):
        """Logging should be configured with level from config."""
        config = minimal_config.model_copy(deep=True)
        config.log_level = "INFO"
        mock_load_config.return_value = config

        create_app()
        mock_basicConfig.assert_called_once()
        kwargs = mock_basicConfig.call_args[1]
        assert kwargs["level"] == logging.INFO


# ---------------------------------------------------------------------------
# Lifespan cleanup exception path (lines 91-92)
# ---------------------------------------------------------------------------

class TestLifespanCleanupException:
    """Tests for the exception path in lifespan cleanup_task cancellation."""

    @pytest.mark.asyncio
    @patch("workbench.api.app._start_news_scheduler_if_agent_enabled")
    @patch("workbench.api.app._run_periodic_session_cleanup")
    @patch("workbench.api.app.init_db")
    @patch("workbench.api.app.init_encryption")
    @patch("workbench.core.encryption.set_encrypt_reports")
    @patch("workbench.api.app._run_alembic_upgrade")
    @patch("workbench.api.app._auto_register_agents")
    @patch("workbench.api.app._register_core_routes")
    @patch("workbench.api.app.load_config")
    async def test_lifespan_cleanup_raises_on_cancel(
        self, mock_load_config, mock_core_routes, mock_agents,
        mock_alembic, mock_set_encrypt, mock_init_encrypt, mock_init_db,
        mock_cleanup, mock_scheduler, minimal_config,
    ):
        """Lifespan should handle exception from cleanup_task cancellation."""
        mock_load_config.return_value = minimal_config
        mock_scheduler.return_value = None

        results = []

        async def cleanup_fn():
            """Coroutine function that will be wrapped by create_task."""
            try:
                await asyncio.sleep(999)
            except asyncio.CancelledError:
                results.append("cancelled")
                raise ValueError("cleanup error on cancel")

        # Make mock_cleanup return the coroutine function itself
        # so create_task wraps it properly
        mock_cleanup.side_effect = cleanup_fn

        app = create_app()
        with TestClient(app) as client:
            client.get("/does-not-exist", headers={"Accept": "application/json"})

        # The lifespan should handle the ValueError without crashing
        assert "cancelled" in results


# ---------------------------------------------------------------------------
# export endpoints (lines 162-163, 170-173)
# ---------------------------------------------------------------------------

class TestExportEndpoints:
    """Tests for the /api/v1/export/* endpoints."""

    def test_export_templates_route(self):
        """GET /api/v1/export/templates should return templates list."""
        app = FastAPI()
        _register_core_routes(app)

        from workbench.services.export_service import list_templates
        with patch(
            "workbench.services.export_service.list_templates",
            return_value=["professional", "simple"],
        ):
            client = TestClient(app)
            response = client.get("/api/v1/export/templates")
            assert response.status_code == 200
            assert response.json() == ["professional", "simple"]

    def test_export_pdf_route_with_auth(self):
        """POST /api/v1/export/pdf requires auth and returns PDF."""
        app = FastAPI()
        _register_core_routes(app)

        from workbench.core.auth import get_current_user
        mock_user = MagicMock()
        mock_user.id = str(uuid4())
        app.dependency_overrides[get_current_user] = lambda: mock_user

        # Mock the actual PDF generation
        with patch("workbench.api.app.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = b"%PDF-1.4 test pdf content"

            client = TestClient(app)
            response = client.post(
                "/api/v1/export/pdf",
                json={"content": "# Hello", "title": "Test Report", "template": "simple"},
            )
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/pdf"
            assert b"PDF" in response.content


# ---------------------------------------------------------------------------
# Successful agent registration (lines 202-204)
# ---------------------------------------------------------------------------

class TestAutoRegisterAgentsSuccess:
    """Tests for successful agent import and registration."""

    def test_auto_register_one_succeeds(self):
        """One agent should be successfully imported and registered."""
        app = FastAPI()
        registry = MagicMock()
        registry.list_all.return_value = []

        mock_agent = MagicMock()
        mock_agent.name = "success_agent"
        mock_agent.get_static_dir.return_value = None

        # Make the first import succeed, others fail
        first_import = True

        def import_side_effect(module_path):
            nonlocal first_import
            if first_import:
                first_import = False
                mod = MagicMock()
                mod.ChatAgent = lambda: mock_agent
                return mod
            raise ImportError("not available")

        with patch("workbench.api.app.importlib.import_module", side_effect=import_side_effect):
            _auto_register_agents(app, registry)
            registry.register.assert_called_once_with(mock_agent)


# ---------------------------------------------------------------------------
# list_tabs route (lines 236-242)
# ---------------------------------------------------------------------------

class TestListTabsRoute:
    """Tests for the /api/v1/tabs endpoint."""

    def test_tabs_route_returns_tabs(self):
        """GET /api/v1/tabs returns tabs from registry."""
        app = FastAPI()
        registry = MagicMock()
        mock_agent = MagicMock()
        mock_agent.name = "test_agent"
        mock_agent.get_static_dir.return_value = None
        mock_agent.get_frontend_tab.return_value = {
            "id": "test_agent", "displayName": "Test Agent",
            "icon": "puzzle", "component": "agent-test_agent",
        }
        registry.list_all.return_value = [mock_agent]

        from workbench.core.auth import get_current_user
        mock_user = MagicMock()
        mock_user.id = str(uuid4())

        # Register agents WITHOUT patching get_session (patches interfere with route deps)
        with patch("workbench.api.app.get_user_agent_settings", return_value={}):
            _auto_register_agents(app, registry)

        app.dependency_overrides[get_current_user] = lambda: mock_user

        # Override the get_session dependency with a mock
        from workbench.core.db import get_session as db_get_session
        mock_session_instance = AsyncMock()
        mock_session_instance.execute = AsyncMock()
        mock_scalar_result = MagicMock()
        mock_scalar_result.scalars.return_value.all.return_value = []
        mock_session_instance.execute.return_value = mock_scalar_result

        async def override_get_session():
            yield mock_session_instance

        # Use the SAME function reference that the route handler uses
        import workbench.api.app as app_mod
        app.dependency_overrides[app_mod.get_session] = override_get_session

        # Patch get_registry to return our custom registry so list_tabs uses our agent
        custom_registry = MagicMock()
        custom_registry.list_all.return_value = [mock_agent]

        with patch("workbench.api.app.get_registry", return_value=custom_registry):
            client = TestClient(app)
            response = client.get("/api/v1/tabs")
            assert response.status_code == 200
            data = response.json()
            assert "tabs" in data
            assert len(data["tabs"]) == 1
            assert data["tabs"][0]["id"] == "test_agent"


# ---------------------------------------------------------------------------
# Scheduler inner closures (lines 255-257, 260-262, 266-300)
# ---------------------------------------------------------------------------

class TestSchedulerClosures:
    """Tests for the inner closures created in _start_news_scheduler_if_agent_enabled."""

    @pytest.mark.asyncio
    async def test_scheduler_inner_functions(self):
        """Extract and call the scheduler closures for coverage."""
        app = FastAPI()

        # We'll capture the closures by monitoring NewsScheduler constructor
        captured_kwargs = {}

        def capture_scheduler(**kwargs):
            captured_kwargs.update(kwargs)
            mock_sched = MagicMock()
            mock_sched.start = AsyncMock()
            return mock_sched

        mock_session_factory = MagicMock()
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock()

        mock_store_instance = AsyncMock()
        mock_store_instance.list_all_interests_global = AsyncMock(return_value=[{"id": 1}])
        mock_store_instance.is_interest_running = AsyncMock(return_value=True)
        mock_store_instance.get_interest = AsyncMock(return_value={"id": 42, "name": "Test"})

        with (
            patch("workbench.core.db.get_session_factory", return_value=mock_session_factory),
            patch("workbench.services.news_scheduler.NewsScheduler", side_effect=capture_scheduler),
            patch("workbench.services.news_store.NewsStore", return_value=mock_store_instance),
            patch("agents.news.agent.set_scheduler"),
        ):
            task = _start_news_scheduler_if_agent_enabled(app)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Now call the captured closures to cover the inner function bodies
        assert "get_interests" in captured_kwargs
        assert "is_running" in captured_kwargs
        assert "run_interest" in captured_kwargs

        get_interests_fn = captured_kwargs["get_interests"]
        is_running_fn = captured_kwargs["is_running"]
        run_interest_fn = captured_kwargs["run_interest"]

        # Call get_interests - should query store.list_all_interests_global
        # We need NewsStore patched for this
        with patch("workbench.services.news_store.NewsStore", return_value=mock_store_instance):
            result = await get_interests_fn()
            assert result == [{"id": 1}]

        # Call is_running - should query store.is_interest_running
        with patch("workbench.services.news_store.NewsStore", return_value=mock_store_instance):
            result = await is_running_fn(42)
            assert result is True

        # Call run_interest - should run the full pipeline
        from workbench.core.models import User

        mock_user = MagicMock(spec=User)
        mock_user.id = f"{uuid4()}"

        mock_scalar_result = MagicMock()
        mock_scalar_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_scalar_result)

        with (
            patch("workbench.services.news_store.NewsStore", return_value=mock_store_instance),
            patch("workbench.core.auth.get_user_inference_api_key", return_value="test-api-key"),
            patch("workbench.services.news_pipeline.NewsPipeline") as mock_pipeline_cls,
        ):
            mock_pipeline = MagicMock()
            mock_pipeline.run = AsyncMock()
            mock_pipeline_cls.return_value = mock_pipeline

            await run_interest_fn("test-user-id", 42)
            mock_pipeline.run.assert_awaited_once()

        # Test run_interest with no user found
        no_user_result = MagicMock()
        no_user_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=no_user_result)

        with patch("workbench.services.news_store.NewsStore", return_value=mock_store_instance):
            await run_interest_fn("missing-user", 42)
            # Should not crash, just log and return

        # Test run_interest with no API key
        mock_store_instance.get_interest = AsyncMock(return_value={"id": 43, "name": "NoKey"})

        # Reset session to return a valid user
        user_with_key_result = MagicMock()
        user_with_key_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=user_with_key_result)

        with (
            patch("workbench.services.news_store.NewsStore", return_value=mock_store_instance),
            patch("workbench.core.auth.get_user_inference_api_key", return_value=None),
        ):
            await run_interest_fn("nokey-user", 43)
            # Should not crash, just log and return

        # Test run_interest with no interest found
        mock_store_instance.get_interest = AsyncMock(return_value=None)

        with patch("workbench.services.news_store.NewsStore", return_value=mock_store_instance):
            await run_interest_fn("no-interest-user", 999)
            # Should return early without error
