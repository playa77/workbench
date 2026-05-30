from caw.skills.loader import SkillDocument


def _seed_skills(client) -> None:
    services = client.app.state.services
    services.skill_registry._skills["skill.pro"] = SkillDocument(
        skill_id="skill.pro", version="1", name="Pro", description="", author="", body="argue pro"
    )
    services.skill_registry._skills["skill.con"] = SkillDocument(
        skill_id="skill.con", version="1", name="Con", description="", author="", body="argue con"
    )


def _run_payload() -> dict[str, object]:
    return {
        "question": "Should we launch?",
        "session_id": "s1",
        "rounds": 0,
        "frames": [
            {"frame_id": "pro", "skill_id": "skill.pro", "label": "Pro"},
            {"frame_id": "con", "skill_id": "skill.con", "label": "Con"},
        ],
    }


def test_deliberation_run_endpoint(client) -> None:
    _seed_skills(client)
    response = client.post("/api/v1/deliberation/run", json=_run_payload())
    assert response.status_code == 200
    assert response.json()["data"]["id"]


def test_deliberation_get_endpoint(client) -> None:
    _seed_skills(client)
    run = client.post("/api/v1/deliberation/run", json=_run_payload()).json()["data"]
    response = client.get(f"/api/v1/deliberation/{run['id']}")
    assert response.status_code == 200
    assert response.json()["data"]["result"]["question"] == "Should we launch?"


def test_deliberation_surface_endpoint(client) -> None:
    _seed_skills(client)
    run = client.post("/api/v1/deliberation/run", json=_run_payload()).json()["data"]
    response = client.get(f"/api/v1/deliberation/{run['id']}/surface")
    assert response.status_code == 200
    assert "surface" in response.json()["data"]
