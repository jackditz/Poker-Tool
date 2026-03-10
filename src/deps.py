"""Shared FastAPI dependencies."""

from sqlalchemy.orm import Session, sessionmaker

# Module-level session factory — set by app startup or overridden by tests
_session_factory: sessionmaker[Session] | None = None


def set_session_factory(factory: sessionmaker[Session], force: bool = False):
    global _session_factory
    if _session_factory is not None and not force:
        return  # Already set (e.g. by tests) — don't override
    _session_factory = factory


def reset_session_factory():
    """Clear the factory (for test cleanup)."""
    global _session_factory
    _session_factory = None


def get_db():
    """Dependency that yields a database session."""
    assert _session_factory is not None, "Database not initialized. Call set_session_factory first."
    db = _session_factory()
    try:
        yield db
    finally:
        db.close()
