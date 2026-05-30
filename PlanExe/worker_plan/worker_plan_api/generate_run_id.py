"""
Utilities for generating run IDs shared between worker and frontend.
"""
import uuid

def generate_run_id() -> str:
    """Generate a UUID-based identifier for a run/task."""
    return str(uuid.uuid4())


if __name__ == "__main__":
    print(generate_run_id())
