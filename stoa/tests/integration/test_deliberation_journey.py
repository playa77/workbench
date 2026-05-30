from fastapi.testclient import TestClient


def test_deliberation_journey(client: TestClient) -> None:
    response = client.post(
        "/api/v1/deliberation/run",
        json={
            "question": "Should we prioritize reliability over speed?",
            "session_id": "d1",
            "frames": [
                {
                    "frame_id": "f1",
                    "skill_id": "caw.builtin.deliberation_director",
                    "label": "Reliability-first",
                },
                {
                    "frame_id": "f2",
                    "skill_id": "caw.builtin.critique_agent",
                    "label": "Speed-first",
                },
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["result"]["positions"]
    assert data["result"]["disagreement_surface"]

    trace_id = data["id"]
    trace = client.get(f"/api/v1/traces/{trace_id}")
    event_types = {event["event_type"] for event in trace.json()["data"]}
    assert "deliberation:started" in event_types
    assert "deliberation:completed" in event_types
