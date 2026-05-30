from caw.errors import (
    CAWError,
    CheckpointError,
    ConfigError,
    EvaluationError,
    PermissionError_,
    ProviderError,
    SkillError,
    StorageError,
    TraceError,
    ValidationError_,
    WorkspaceError,
)


def test_caw_error_defaults() -> None:
    err = CAWError("msg", "code")
    assert err.message == "msg"
    assert err.code == "code"
    assert err.details == {}


def test_caw_error_details_and_repr() -> None:
    err = CAWError("msg", "code", {"key": "val"})
    assert err.details == {"key": "val"}
    assert repr(err) == "CAWError(code='code', message='msg')"


def test_subclasses_are_exceptions() -> None:
    for cls in [
        ConfigError,
        StorageError,
        ProviderError,
        SkillError,
        WorkspaceError,
        PermissionError_,
        ValidationError_,
        CheckpointError,
        EvaluationError,
        TraceError,
    ]:
        instance = cls("x", "y")
        assert isinstance(instance, CAWError)
        assert isinstance(instance, Exception)
