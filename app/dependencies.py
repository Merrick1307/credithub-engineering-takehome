"""Dependency injection for database connections.

Provides pooled database access with a single AsyncGenerator dependency for FastAPI.
The connection pool is managed by the lifespan context manager in main.py.
"""

from typing import AsyncGenerator
from sqlalchemy.orm import Session

# Global pool initialized by lifespan context manager
_session_local = None


async def get_db() -> AsyncGenerator[Session, None]:
    """FastAPI dependency — yields a session from the pool, always closes it.

    The underlying pool (created in lifespan context manager) ensures
    connections are efficiently reused.
    """
    if _session_local is None:
        raise RuntimeError(
            "Database session factory not initialized. "
            "Ensure lifespan context manager has run."
        )

    db = _session_local()
    try:
        yield db
    finally:
        db.close()


def set_session_factory(factory):
    """Called by lifespan context manager to inject the session factory."""
    global _session_local
    _session_local = factory


def get_session_factory():
    """Return the current session factory (for testing/debugging)."""
    return _session_local
