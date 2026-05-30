import uuid

from worker_plan_api.generate_run_id import generate_run_id


def test_generate_run_id_is_uuid():
    run_id = generate_run_id()
    parsed = uuid.UUID(run_id)
    assert str(parsed) == run_id
