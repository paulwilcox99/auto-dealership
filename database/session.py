"""DB engine / session factory.  Switch backends by changing DB_DRIVER in .env."""

import os
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from config import DB_DIR, DB_DRIVER


def _sqlite_engine(db_filename: str):
    """Create a SQLite engine for a single DB file."""
    os.makedirs(DB_DIR, exist_ok=True)
    path = os.path.join(DB_DIR, db_filename)
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )
    # Enable WAL mode for concurrent reads by external programs
    @event.listens_for(engine, "connect")
    def set_wal(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def get_engine(db_filename: str):
    """Return an engine for the given DB file, based on DB_DRIVER."""
    if DB_DRIVER == "sqlite":
        return _sqlite_engine(db_filename)
    # Future: elif DB_DRIVER == "postgresql": return _pg_engine(...)
    raise ValueError(f"Unsupported DB_DRIVER: {DB_DRIVER!r}")


def get_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(engine) -> Session:
    """Return a single session (caller is responsible for close)."""
    factory = get_session_factory(engine)
    return factory()


# ── Named engine/session pairs for all databases ─────────────────────────────

_engines: dict = {}


def engine_for(db_filename: str):
    if db_filename not in _engines:
        _engines[db_filename] = get_engine(db_filename)
    return _engines[db_filename]


def session_for(db_filename: str) -> Session:
    return get_session(engine_for(db_filename))
