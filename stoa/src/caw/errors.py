"""Base exception hierarchy for CAW.

All CAW-specific exceptions inherit from CAWError.
Each layer has its own exception subclass.
"""


class CAWError(Exception):
    """Base exception for all CAW errors.

    Attributes:
        message: Human-readable error description.
        code: Machine-readable error code string.
        details: Optional dictionary with additional context.
    """

    def __init__(
        self,
        message: str,
        code: str,
        details: dict[str, object] | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"


class ConfigError(CAWError):
    """Configuration loading or validation error."""


class StorageError(CAWError):
    """Database or file storage error."""


class ProviderError(CAWError):
    """Model provider communication error."""


class SkillError(CAWError):
    """Skill loading, validation, or resolution error."""


class WorkspaceError(CAWError):
    """File or workspace operation error."""


class PermissionError_(CAWError):  # noqa: N801, N818
    """Permission check or approval gate error."""


class ValidationError_(CAWError):  # noqa: N801, N818
    """Input validation error."""


class CheckpointError(CAWError):
    """Checkpoint save or restore error."""


class EvaluationError(CAWError):
    """Evaluation task or scoring error."""


class TraceError(CAWError):
    """Trace collection or retrieval error."""
