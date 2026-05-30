"""Evaluation task loading and validation utilities."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from caw.errors import EvaluationError

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class EvalTaskInput:
    """Input definition for an evaluation task."""

    type: str
    sources: list[Path]
    query: str | None = None
    command: str | None = None
    file: Path | None = None


@dataclass(frozen=True)
class EvalTaskExpected:
    """Expected-output constraints for an evaluation task."""

    type: str
    constraints: dict[str, object]


@dataclass(frozen=True)
class EvalTaskScoring:
    """Scorer list and weighting map for an evaluation task."""

    scorers: list[str]
    weights: dict[str, float]


@dataclass(frozen=True)
class EvalTask:
    """In-memory representation of a task TOML file."""

    task_id: str
    version: str
    name: str
    description: str
    category: str
    difficulty: str
    input: EvalTaskInput
    expected: EvalTaskExpected
    scoring: EvalTaskScoring
    source_path: Path


def _require_table(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise EvaluationError(
            message=f"Task file is missing required table [{name}]",
            code="eval_task_missing_table",
            details={"table": name},
        )
    return value


def _require_str(data: dict[str, Any], key: str, table: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(
            message=f"Task field '{table}.{key}' is required and must be a non-empty string",
            code="eval_task_invalid_field",
            details={"table": table, "field": key},
        )
    return value


def load_task(path: Path) -> EvalTask:
    """Load and validate a task definition from a TOML file."""
    task_path = path.expanduser().resolve()
    try:
        parsed = tomllib.loads(task_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvaluationError(
            message=f"Task file not found: {task_path}",
            code="eval_task_not_found",
            details={"path": str(task_path)},
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise EvaluationError(
            message=f"Failed to parse task TOML at {task_path}: {exc}",
            code="eval_task_invalid_toml",
            details={"path": str(task_path)},
        ) from exc

    task_table = _require_table(parsed, "task")
    input_table = _require_table(task_table, "input")
    expected_table = _require_table(task_table, "expected")
    scoring_table = _require_table(task_table, "scoring")

    raw_sources = input_table.get("sources", [])
    if not isinstance(raw_sources, list) or not all(isinstance(item, str) for item in raw_sources):
        raise EvaluationError(
            message="Task field 'task.input.sources' must be a list of string paths",
            code="eval_task_invalid_field",
            details={"table": "task.input", "field": "sources"},
        )

    resolved_sources = [(task_path.parent / item).resolve() for item in raw_sources]

    raw_scorers = scoring_table.get("scorers", [])
    if not isinstance(raw_scorers, list) or not all(isinstance(item, str) for item in raw_scorers):
        raise EvaluationError(
            message="Task field 'task.scoring.scorers' must be a list of scorer IDs",
            code="eval_task_invalid_field",
            details={"table": "task.scoring", "field": "scorers"},
        )

    raw_weights = scoring_table.get("weights", {})
    if not isinstance(raw_weights, dict):
        raise EvaluationError(
            message="Task field 'task.scoring.weights' must be a TOML inline table",
            code="eval_task_invalid_field",
            details={"table": "task.scoring", "field": "weights"},
        )

    weights: dict[str, float] = {}
    for scorer_id, value in raw_weights.items():
        if not isinstance(scorer_id, str) or not isinstance(value, (int, float)):
            raise EvaluationError(
                message="Task scoring weights must map scorer IDs to numeric values",
                code="eval_task_invalid_field",
                details={"table": "task.scoring", "field": "weights"},
            )
        weights[scorer_id] = float(value)

    expected_constraints = {key: value for key, value in expected_table.items() if key != "type"}

    return EvalTask(
        task_id=_require_str(task_table, "task_id", "task"),
        version=_require_str(task_table, "version", "task"),
        name=_require_str(task_table, "name", "task"),
        description=_require_str(task_table, "description", "task"),
        category=_require_str(task_table, "category", "task"),
        difficulty=_require_str(task_table, "difficulty", "task"),
        input=EvalTaskInput(
            type=_require_str(input_table, "type", "task.input"),
            sources=resolved_sources,
            query=input_table.get("query") if isinstance(input_table.get("query"), str) else None,
            command=(
                input_table.get("command") if isinstance(input_table.get("command"), str) else None
            ),
            file=(
                (task_path.parent / input_table["file"]).resolve()
                if isinstance(input_table.get("file"), str)
                else None
            ),
        ),
        expected=EvalTaskExpected(
            type=_require_str(expected_table, "type", "task.expected"),
            constraints=expected_constraints,
        ),
        scoring=EvalTaskScoring(scorers=raw_scorers, weights=weights),
        source_path=task_path,
    )


def load_tasks(tasks_dir: Path) -> list[EvalTask]:
    """Load all task TOML files from a directory tree."""
    resolved = tasks_dir.expanduser().resolve()
    if not resolved.exists():
        return []
    task_files = sorted(resolved.glob("**/*.toml"))
    return [load_task(task_file) for task_file in task_files]
