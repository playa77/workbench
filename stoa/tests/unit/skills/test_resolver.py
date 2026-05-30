from caw.errors import SkillError
from caw.skills.loader import SkillDocument
from caw.skills.resolver import SkillResolver


def _skill(
    skill_id: str, priority: int = 100, conflicts_with: list[str] | None = None
) -> SkillDocument:
    return SkillDocument(
        skill_id=skill_id,
        version="1.0.0",
        name=skill_id,
        description="desc",
        author="test",
        body=f"# {skill_id}\n\nBody content for {skill_id}",
        priority=priority,
        conflicts_with=conflicts_with or [],
    )


def test_resolve_empty() -> None:
    resolver = SkillResolver([])
    result = resolver.resolve()
    assert result.skills == []
    assert result.composed_context == ""


def test_resolve_single_explicit() -> None:
    resolver = SkillResolver([_skill("a.b")])
    result = resolver.resolve(explicit_ids=["a.b"])
    assert [skill.skill_id for skill in result.skills] == ["a.b"]


def test_resolve_priority_order() -> None:
    resolver = SkillResolver([_skill("a.low", priority=10), _skill("a.high", priority=200)])
    result = resolver.resolve(explicit_ids=["a.high", "a.low"])
    assert [skill.skill_id for skill in result.skills] == ["a.low", "a.high"]


def test_resolve_conflict_by_priority() -> None:
    low = _skill("a.low", priority=10, conflicts_with=["a.high"])
    high = _skill("a.high", priority=200, conflicts_with=["a.low"])
    resolver = SkillResolver([low, high])
    result = resolver.resolve(explicit_ids=["a.low", "a.high"])
    assert [skill.skill_id for skill in result.skills] == ["a.high"]


def test_resolve_conflict_by_specificity() -> None:
    builtin = _skill("a.base", priority=100, conflicts_with=["a.override"])
    explicit = _skill("a.override", priority=100, conflicts_with=["a.base"])
    resolver = SkillResolver([builtin, explicit])
    result = resolver.resolve(explicit_ids=["a.override"], builtin_ids=["a.base"])
    assert [skill.skill_id for skill in result.skills] == ["a.override"]


def test_resolve_unresolvable_conflict() -> None:
    left = _skill("a.left", priority=100, conflicts_with=["a.right"])
    right = _skill("a.right", priority=100, conflicts_with=["a.left"])
    resolver = SkillResolver([left, right])
    try:
        resolver.resolve(explicit_ids=["a.left", "a.right"])
    except SkillError as exc:
        assert "a.left" in exc.message and "a.right" in exc.message
    else:  # pragma: no cover - defensive guard for strict pytest style
        raise AssertionError("Expected SkillError for unresolvable conflict")


def test_composed_context_has_delimiters() -> None:
    resolver = SkillResolver([_skill("a.b")])
    result = resolver.resolve(explicit_ids=["a.b"])
    assert "<!-- BEGIN SKILL: a.b -->" in result.composed_context
    assert "<!-- END SKILL: a.b -->" in result.composed_context


def test_missing_skill_warning() -> None:
    resolver = SkillResolver([])
    result = resolver.resolve(explicit_ids=["missing.skill"])
    assert result.warnings


def test_resolve_with_pack_and_explicit() -> None:
    resolver = SkillResolver([_skill("a.explicit"), _skill("a.pack")])
    result = resolver.resolve(explicit_ids=["a.explicit"], pack_ids=["a.pack"])
    assert [skill.skill_id for skill in result.skills] == ["a.explicit", "a.pack"]
