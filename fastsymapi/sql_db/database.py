"""Database connection and session management.

Single Responsibility: This module handles database engine creation,
session factory configuration, and dependency injection for FastAPI.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./fsymapi.db"


def _set_sqlite_pragmas(dbapi_connection, connection_record):  # pragma: no cover - exercised via sqlite driver
    """Enable WAL mode for concurrent readers/writers on the SQLite backend."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_size=20,
    max_overflow=30,
)

event.listen(engine, "connect", _set_sqlite_pragmas)

session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = session_local()
    try:
        yield db
    finally:
        db.close()
