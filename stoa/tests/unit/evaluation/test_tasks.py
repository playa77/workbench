from pathlib import Path

import pytest

from caw.errors import EvaluationError
from caw.evaluation.tasks import load_task


def test_load_valid_task() -> None:
    task = load_task(Path("tests/fixtures/tasks/sample_task.toml"))
    assert task.task_id == "research.sample"
    assert task.input.query == "Summarize the provided source."
    assert task.scoring.weights["latency"] == 0.4
    assert task.input.sources[0].name == "source_a.md"


def test_load_invalid_task(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.toml"
    invalid.write_text("[task]\nname='missing id'\n", encoding="utf-8")

    with pytest.raises(EvaluationError) as exc:
        load_task(invalid)

    assert "missing required table [input]" in exc.value.message
