from pathlib import Path

from caw.core.config import SkillsConfig
from caw.models import SessionMode
from caw.skills.registry import SkillRegistry


def _write_skill(path: Path, skill_id: str) -> None:
    path.write_text(
        "\n".join(
            [
                "---",
                f'skill_id: "{skill_id}"',
                'version: "1.0.0"',
                f'name: "{skill_id}"',
                'description: "desc"',
                'author: "test"',
                "---",
                "",
                f"# {skill_id}",
                "",
                "Valid skill body content.",
            ]
        ),
        encoding="utf-8",
    )


def test_load_from_directories(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin"
    user_dir = tmp_path / "user"
    packs_dir = tmp_path / "packs"
    builtin_dir.mkdir()
    user_dir.mkdir()
    packs_dir.mkdir()

    _write_skill(builtin_dir / "builtin.md", "caw.builtin.alpha")
    _write_skill(user_dir / "user.md", "user.beta")
    (packs_dir / "pack.toml").write_text(
        "\n".join(
            [
                "[pack]",
                'pack_id = "p.one"',
                'version = "1.0.0"',
                'name = "one"',
                'description = "one"',
                "",
                "[[pack.skills]]",
                'skill_id = "caw.builtin.alpha"',
            ]
        ),
        encoding="utf-8",
    )

    registry = SkillRegistry(
        SkillsConfig(
            builtin_dir=str(builtin_dir),
            user_dir=str(user_dir),
            packs_dir=str(packs_dir),
        )
    )
    registry.load()

    assert len(registry.list_skills()) == 2
    assert len(registry.list_packs()) == 1


def test_get_skill_by_id(tmp_path: Path) -> None:
    skill_dir = tmp_path / "builtin"
    skill_dir.mkdir()
    _write_skill(skill_dir / "one.md", "caw.builtin.alpha")
    registry = SkillRegistry(
        SkillsConfig(
            builtin_dir=str(skill_dir), user_dir=str(tmp_path / "u"), packs_dir=str(tmp_path / "p")
        )
    )
    registry.load()
    assert registry.get_skill("caw.builtin.alpha") is not None


def test_get_skill_not_found(tmp_path: Path) -> None:
    registry = SkillRegistry(
        SkillsConfig(
            builtin_dir=str(tmp_path / "b"),
            user_dir=str(tmp_path / "u"),
            packs_dir=str(tmp_path / "p"),
        )
    )
    registry.load()
    assert registry.get_skill("missing") is None


def test_mode_defaults() -> None:
    registry = SkillRegistry(SkillsConfig())
    assert registry.get_mode_defaults(SessionMode.CHAT) == []
    assert registry.get_mode_defaults(SessionMode.RESEARCH) == ["caw.builtin.research_operator"]
    assert registry.get_mode_defaults(SessionMode.DELIBERATION) == [
        "caw.builtin.deliberation_director"
    ]
    assert registry.get_mode_defaults(SessionMode.WORKSPACE) == ["caw.builtin.workspace_operator"]
    assert registry.get_mode_defaults(SessionMode.ARENA) == []


def test_create_resolver(tmp_path: Path) -> None:
    skill_dir = tmp_path / "builtin"
    skill_dir.mkdir()
    _write_skill(skill_dir / "one.md", "caw.builtin.alpha")
    registry = SkillRegistry(
        SkillsConfig(
            builtin_dir=str(skill_dir), user_dir=str(tmp_path / "u"), packs_dir=str(tmp_path / "p")
        )
    )
    registry.load()
    resolver = registry.create_resolver()
    result = resolver.resolve(explicit_ids=["caw.builtin.alpha"])
    assert [skill.skill_id for skill in result.skills] == ["caw.builtin.alpha"]
