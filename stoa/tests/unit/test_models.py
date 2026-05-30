from datetime import UTC

from caw.models import (
    ArtifactType,
    Message,
    MessageRole,
    PermissionLevel,
    Session,
    SessionMode,
    SessionState,
    _generate_id,
    _utcnow,
)


def test_session_defaults() -> None:
    session = Session()
    assert session.id
    assert session.state == SessionState.CREATED
    assert session.mode == SessionMode.CHAT
    assert session.config_overrides == {}


def test_session_state_enum() -> None:
    assert SessionState("active") == SessionState.ACTIVE


def test_message_defaults() -> None:
    message = Message()
    assert message.role == MessageRole.USER
    assert message.sequence_num == 0


def test_generate_id_unique() -> None:
    ids = {_generate_id() for _ in range(100)}
    assert len(ids) == 100


def test_utcnow_is_utc() -> None:
    assert _utcnow().tzinfo == UTC


def test_all_enums_are_str_enum() -> None:
    values = [
        SessionState.ACTIVE,
        SessionMode.CHAT,
        MessageRole.ASSISTANT,
        ArtifactType.FILE,
        PermissionLevel.WRITE,
    ]
    assert all(isinstance(value, str) for value in values)
