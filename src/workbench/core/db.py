"""Async database session factory — compatibility shim.

Delegates to workbench.shared.db.session for the canonical implementation.
"""



from workbench.core.config import WorkbenchConfig
from workbench.shared.db.session import (
    DatabaseConfig,
    close_db,
    get_engine,
    get_session,
    get_session_factory,
)
from workbench.shared.db.session import (
    init_db as _init_shared_db,
)

__all__ = ["close_db", "get_engine", "get_session", "get_session_factory", "init_db"]


def init_db(config: WorkbenchConfig) -> None:
    db_cfg = DatabaseConfig(
        url=config.database_url or "",
        echo=(config.log_level == "DEBUG"),
    )
    _init_shared_db(db_cfg)
