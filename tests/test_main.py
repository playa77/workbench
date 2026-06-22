"""Tests for workbench.main — CLI entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from workbench.main import main, _create_user_only, _run_migrations, _run_alembic_upgrade


# ---------------------------------------------------------------------------
# main() — CLI dispatch
# ---------------------------------------------------------------------------

class TestMainCLI:
    """Tests for main() — argparse-based CLI dispatch."""

    @patch("workbench.main.load_config")
    @patch("workbench.main.create_app")
    @patch("workbench.main.uvicorn.run")
    def test_serve_default(self, mock_uvicorn, mock_create_app, mock_load_config):
        """'serve' command should use host/port from config."""
        mock_config = MagicMock()
        mock_config.api_host = "127.0.0.1"
        mock_config.api_port = 8420
        mock_config.log_level = "INFO"
        mock_load_config.return_value = mock_config

        with patch.object(sys, "argv", ["workbench", "serve"]):
            main()

        mock_create_app.assert_called_once_with(mock_config)
        mock_uvicorn.assert_called_once_with(
            mock_create_app.return_value,
            host="127.0.0.1",
            port=8420,
            log_level="info",
        )

    @patch("workbench.main.load_config")
    @patch("workbench.main.create_app")
    @patch("workbench.main.uvicorn.run")
    def test_serve_with_host_port_args(
        self, mock_uvicorn, mock_create_app, mock_load_config
    ):
        """'serve --host --port' should override config defaults."""
        mock_config = MagicMock()
        mock_config.api_host = "127.0.0.1"
        mock_config.api_port = 8420
        mock_config.log_level = "INFO"
        mock_load_config.return_value = mock_config

        with patch.object(sys, "argv", ["workbench", "serve", "--host", "0.0.0.0", "--port", "9090"]):
            main()

        mock_uvicorn.assert_called_once_with(
            mock_create_app.return_value,
            host="0.0.0.0",
            port=9090,
            log_level="info",
        )

    @patch("builtins.print")
    def test_version(self, mock_print):
        """'version' command should print version and return."""
        with patch.object(sys, "argv", ["workbench", "version"]):
            with patch("workbench.__version__.__version__", "0.1.0"):
                main()

        mock_print.assert_called_once_with("Workbench v0.1.0")

    @patch("workbench.main.load_config")
    @patch("workbench.main._run_migrations")
    def test_init_db(self, mock_run_migrations, mock_load_config):
        """'init-db' command should run migrations."""
        mock_config = MagicMock()
        mock_load_config.return_value = mock_config

        with patch.object(sys, "argv", ["workbench", "init-db"]):
            main()

        mock_load_config.assert_called_once()
        mock_run_migrations.assert_called_once_with(mock_config)

    @patch("workbench.main.load_config")
    @patch("workbench.core.db.init_db")
    @patch("workbench.main.asyncio.run")
    @patch("builtins.print")
    def test_create_user(
        self,
        mock_print,
        mock_asyncio_run,
        mock_init_db,
        mock_load_config,
    ):
        """'create-user' command should create a user."""
        mock_config = MagicMock()
        mock_config.smtp_host = "smtp.example.com"  # SMTP configured -> no warning
        mock_load_config.return_value = mock_config

        with patch.object(
            sys, "argv",
            ["workbench", "create-user", "--username", "alice", "--email", "a@b.com", "--password", "secret"],
        ):
            main()

        mock_asyncio_run.assert_called_once()
        # Verify the correct function was called with user data
        args, _ = mock_asyncio_run.call_args
        coro = args[0]
        assert coro.__name__ == "_create_user_only"
        assert coro.cr_frame.f_locals["username"] == "alice"
        assert coro.cr_frame.f_locals["email"] == "a@b.com"
        assert coro.cr_frame.f_locals["password"] == "secret"
        assert coro.cr_frame.f_locals["is_admin"] is False
        mock_init_db.assert_called_once_with(mock_config)

    @patch("workbench.main.load_config")
    @patch("workbench.core.db.init_db")
    @patch("workbench.main.asyncio.run")
    @patch("builtins.print")
    def test_create_user_smtp_warning(
        self,
        mock_print,
        mock_asyncio_run,
        mock_init_db,
        mock_load_config,
    ):
        """Should print SMTP warning when smtp_host not set."""
        mock_config = MagicMock()
        mock_config.smtp_host = ""  # No SMTP config
        mock_load_config.return_value = mock_config

        with patch.object(
            sys, "argv",
            ["workbench", "create-user", "--username", "bob", "--email", "b@c.com", "--password", "pass"],
        ):
            main()

        mock_print.assert_any_call(
            "WARNING: SMTP is not configured. Email features will not work."
        )

    @patch("workbench.main.load_config")
    @patch("workbench.core.db.init_db")
    @patch("workbench.main.asyncio.run")
    def test_create_user_admin(self, mock_asyncio_run, mock_init_db, mock_load_config):
        """'create-user --admin' should grant admin privileges."""
        mock_config = MagicMock()
        mock_config.smtp_host = ""
        mock_load_config.return_value = mock_config

        with patch.object(
            sys, "argv",
            ["workbench", "create-user", "--username", "admin", "--email", "a@d.com", "--password", "adminpass", "--admin"],
        ):
            main()

        args, _ = mock_asyncio_run.call_args
        coro = args[0]
        assert coro.cr_frame.f_locals["is_admin"] is True

    def test_no_command_shows_help(self):
        """No subcommand should call parser.print_help()."""
        with patch.object(sys, "argv", ["workbench"]):
            with patch("workbench.main.argparse.ArgumentParser.print_help") as mock_help:
                main()
                mock_help.assert_called_once()

    def test_serve_lowercases_log_level(self):
        """Log level should be lowercased for uvicorn."""
        mock_config = MagicMock()
        mock_config.api_host = "0.0.0.0"
        mock_config.api_port = 8000
        mock_config.log_level = "DEBUG"

        with (
            patch.object(sys, "argv", ["workbench", "serve"]),
            patch("workbench.main.load_config", return_value=mock_config),
            patch("workbench.main.create_app"),
            patch("workbench.main.uvicorn.run") as mock_uvicorn,
        ):
            main()
            mock_uvicorn.assert_called_once()
            assert mock_uvicorn.call_args[1]["log_level"] == "debug"


# ---------------------------------------------------------------------------
# _create_user_only
# ---------------------------------------------------------------------------

class TestCreateUserOnly:
    """Tests for _create_user_only()."""

    async def test_create_user_success(self):
        """Should create user and print details."""
        with (
            patch("workbench.core.db.close_db") as mock_close_db,
            patch("workbench.core.db.get_session_factory") as mock_get_session_factory,
            patch("workbench.core.db.get_engine") as mock_get_engine,
            patch("workbench.core.auth.hash_password") as mock_hash_password,
            patch("builtins.print") as mock_print,
        ):
            mock_hash_password.return_value = "hashed_pw"

            # Engine mock: begin() returns async context manager
            mock_engine = MagicMock()
            mock_begin_cm = AsyncMock()
            mock_begin_cm.__aenter__.return_value = AsyncMock()
            mock_begin_cm.__aexit__.return_value = None
            mock_engine.begin.return_value = mock_begin_cm
            mock_get_engine.return_value = mock_engine

            # Session mock: execute() returns coroutine resolving to MagicMock
            mock_session = MagicMock()
            mock_session.commit = AsyncMock()
            mock_exec_result = MagicMock()
            mock_exec_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_exec_result)
            mock_session_factory = MagicMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_session_factory.return_value = mock_session_factory

            await _create_user_only(username="alice", email="a@b.com", password="secret")

            mock_hash_password.assert_called_once_with("secret")
            mock_session.add.assert_called_once()
            mock_session.commit.assert_awaited_once()
            mock_close_db.assert_awaited_once()

            # Check print calls include user details
            mock_print.assert_any_call("Username: alice")
            mock_print.assert_any_call("Email: a@b.com")
            mock_print.assert_any_call("Role: user")

    async def test_create_user_admin_role(self):
        """Admin user should show 'admin' role."""
        with (
            patch("workbench.core.db.close_db") as mock_close_db,
            patch("workbench.core.db.get_session_factory") as mock_get_session_factory,
            patch("workbench.core.db.get_engine") as mock_get_engine,
            patch("workbench.core.auth.hash_password") as mock_hash_password,
            patch("builtins.print") as mock_print,
        ):
            mock_hash_password.return_value = "hashed_pw"

            # Engine mock
            mock_engine = MagicMock()
            mock_begin_cm = AsyncMock()
            mock_begin_cm.__aenter__.return_value = AsyncMock()
            mock_begin_cm.__aexit__.return_value = None
            mock_engine.begin.return_value = mock_begin_cm
            mock_get_engine.return_value = mock_engine

            # Session mock
            mock_session = MagicMock()
            mock_session.commit = AsyncMock()
            mock_exec_result = MagicMock()
            mock_exec_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_exec_result)
            mock_session_factory = MagicMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_session_factory.return_value = mock_session_factory

            await _create_user_only(username="admin", email="a@d.com", password="adminpass", is_admin=True)

            mock_print.assert_any_call("Role: admin")
            # Verify User was created with is_admin=True
            added_user = mock_session.add.call_args[0][0]
            assert added_user.is_admin is True

    async def test_create_user_already_exists(self):
        """Should abort when user already exists."""
        with (
            patch("workbench.core.db.close_db") as mock_close_db,
            patch("workbench.core.db.get_session_factory") as mock_get_session_factory,
            patch("workbench.core.db.get_engine") as mock_get_engine,
            patch("workbench.core.auth.hash_password") as mock_hash_password,
            patch("builtins.print") as mock_print,
        ):
            # Engine mock
            mock_engine = MagicMock()
            mock_begin_cm = AsyncMock()
            mock_begin_cm.__aenter__.return_value = AsyncMock()
            mock_begin_cm.__aexit__.return_value = None
            mock_engine.begin.return_value = mock_begin_cm
            mock_get_engine.return_value = mock_engine

            # Session mock: existing user found
            mock_session = MagicMock()
            mock_exec_result = MagicMock()
            mock_exec_result.scalar_one_or_none.return_value = MagicMock()  # existing user
            mock_session.execute = AsyncMock(return_value=mock_exec_result)
            mock_session_factory = MagicMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_session_factory.return_value = mock_session_factory

            await _create_user_only(username="alice", email="a@b.com", password="secret")

            # Should have printed warning and NOT added a user
            mock_print.assert_called_once_with(
                "User with username 'alice' or email 'a@b.com' already exists."
            )
            mock_session.add.assert_not_called()
            # close_db is NOT called when returning early due to existing user
            mock_close_db.assert_not_awaited()


# ---------------------------------------------------------------------------
# _run_migrations
# ---------------------------------------------------------------------------

class TestRunMigrations:
    """Tests for _run_migrations()."""

    @patch("workbench.core.db.close_db")
    @patch("workbench.core.db.init_db")
    @patch("workbench.main._run_alembic_upgrade")
    def test_run_migrations(self, mock_alembic, mock_init_db, mock_close_db):
        """Should call init_db, alembic upgrade, and close_db."""
        config = MagicMock()
        _run_migrations(config)

        mock_init_db.assert_called_once_with(config)
        mock_alembic.assert_called_once()
        mock_close_db.assert_called_once()


# ---------------------------------------------------------------------------
# _run_alembic_upgrade (main module version)
# ---------------------------------------------------------------------------

class TestRunAlembicUpgradeMain:
    """Tests for _run_alembic_upgrade() in main.py."""

    @patch("alembic.command.upgrade")
    @patch("alembic.config.Config")
    def test_alembic_upgrade_called(self, mock_alembic_cfg_cls, mock_upgrade):
        """Alembic upgrade should be called."""
        mock_cfg = MagicMock()
        mock_alembic_cfg_cls.return_value = mock_cfg

        with patch("workbench.main.Path.exists") as mock_exists:
            mock_exists.return_value = True  # alembic.ini found in source tree
            _run_alembic_upgrade()

        mock_upgrade.assert_called_once_with(mock_cfg, "head")

    @patch("alembic.command.upgrade")
    @patch("alembic.config.Config")
    @patch("builtins.print")
    def test_alembic_upgrade_prints_success(
        self, mock_print, mock_alembic_cfg_cls, mock_upgrade
    ):
        """Should print success message after upgrade."""
        mock_cfg = MagicMock()
        mock_alembic_cfg_cls.return_value = mock_cfg

        with patch("workbench.main.Path.exists") as mock_exists:
            mock_exists.return_value = True
            _run_alembic_upgrade()

        mock_print.assert_called_once_with(
            "Database schema initialized successfully (Alembic upgrade complete)."
        )

    @patch("alembic.command.upgrade")
    @patch("alembic.config.Config")
    def test_alembic_upgrade_fallback_cwd(self, mock_alembic_cfg_cls, mock_upgrade):
        """Should fall back to CWD when alembic.ini not in source tree."""
        mock_cfg = MagicMock()
        mock_alembic_cfg_cls.return_value = mock_cfg

        with (
            patch("workbench.main.Path.exists") as mock_exists,
            patch("workbench.main.Path.cwd") as mock_cwd,
        ):
            mock_exists.return_value = False  # Not in source tree
            mock_cwd.return_value = Path("/docker/workdir")
            _run_alembic_upgrade()

        # Config should be created with CWD path
        expected_ini = str(Path("/docker/workdir") / "alembic.ini")
        mock_alembic_cfg_cls.assert_called_with(expected_ini)
        mock_upgrade.assert_called_once_with(mock_cfg, "head")

    @patch("alembic.command.upgrade")
    def test_alembic_config_script_location(self, mock_upgrade):
        """Alembic config should set script_location."""
        with (
            patch("workbench.main.Path.exists") as mock_exists,
            patch("workbench.main.Path.resolve") as mock_resolve,
        ):
            mock_exists.return_value = True
            mock_root = MagicMock()
            mock_root.parents.__getitem__.return_value = Path("/workbench_root")
            mock_resolve.return_value = mock_root

            mock_cfg = MagicMock()
            with patch("alembic.config.Config", return_value=mock_cfg):
                _run_alembic_upgrade()
                mock_cfg.set_main_option.assert_called_with(
                    "script_location",
                    str(Path("/workbench_root") / "alembic"),
                )


# ---------------------------------------------------------------------------
# __name__ == "__main__" guard (line 142)
# ---------------------------------------------------------------------------


class TestMainGuard:
    """Tests for the if __name__ == '__main__' guard at end of main.py."""

    def test_name_main_guard_calls_main(self):
        """Line 142: __name__ == '__main__' guard should call main()."""
        import importlib.util
        import pathlib
        import workbench.main as mod

        src_path = pathlib.Path(mod.__file__)
        spec = importlib.util.spec_from_file_location("__main__", src_path)
        module = importlib.util.module_from_spec(spec)

        with patch.object(sys, "argv", ["workbench"]):
            with patch("workbench.main.argparse.ArgumentParser.print_help") as mock_help:
                spec.loader.exec_module(module)
                mock_help.assert_called_once()
