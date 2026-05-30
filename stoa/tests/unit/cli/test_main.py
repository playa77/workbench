from pathlib import Path

from click.testing import CliRunner

from caw.cli.main import cli


def test_version_command() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_config_show_redacted(monkeypatch) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("caw.toml").write_text(
            """
[providers.primary]
type = "openai"
api_key_env = "OPENAI_API_KEY"
default_model = "gpt-4o-mini"
""".strip()
        )
        result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert '"api_key_env":"***"' in result.output.replace(" ", "")


def test_db_init() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("caw.toml").write_text(
            """
[general]
data_dir = "./.caw-data"

[storage]
db_path = "./.caw-data/test.db"
""".strip()
        )
        result = runner.invoke(cli, ["db", "init"])
        assert result.exit_code == 0
        assert Path(".caw-data/test.db").exists()


def test_deliberate_command() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("caw.toml").write_text('[storage]\ndb_path = ":memory:"\n')
        result = runner.invoke(cli, ["deliberate", "What should we do?"])
    assert result.exit_code == 0
    assert "Question:" in result.output


def test_eval_run_command() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("caw.toml").write_text(
            """
[storage]
db_path = ":memory:"

[evaluation]
tasks_dir = "./tasks"
""".strip()
        )
        Path("tasks").mkdir()
        result = runner.invoke(cli, ["eval", "run", "missing.task"])
    assert result.exit_code == 0
    assert "Task not found" in result.output


def test_eval_compare_command() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("caw.toml").write_text('[storage]\ndb_path = ":memory:"\n')
        result = runner.invoke(cli, ["eval", "compare", "a", "b"])
    assert result.exit_code == 0
