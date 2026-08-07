"""
DB session management for Phoenix. Own SQLite file (phoenix.db), same
"each subsystem owns its own local DB" precedent as builder.db,
atlas.db, observer.db, workflow_engine.db — nothing outside this
module reaches into these tables directly.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from phoenix.models import Base

DB_PATH = Path(__file__).resolve().parent / "phoenix.db"
DB_URL = f"sqlite:///{DB_PATH}"

_engine = create_engine(DB_URL, connect_args={"check_same_thread": False})

@event.listens_for(_engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create all Phoenix tables if they don't already exist. Safe to
    call repeatedly — `create_all` only creates what's missing."""
    Base.metadata.create_all(bind=_engine)


# Called at import time (not just inside submit_opportunity_discovery)
# so any entry point — list_reports(), get_report(), or a fresh script
# importing this module directly — works against a database that
# already has its tables, rather than only after the first successful
# run. Idempotent, so this is safe on every import.
init_db()


@contextmanager
def get_session() -> Iterator[Session]:
    """Context-managed session. Commits on clean exit, rolls back and
    re-raises on error, always closes.

    Usage:
        with get_session() as session:
            session.add(some_row)
    """
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
