"""Database engine and session helpers."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


def init_db() -> None:
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _check_schema()


def _check_schema() -> None:
    """Fail loudly on a database created by an older version of this code.

    create_all adds missing tables but never missing columns, so an old demo
    database would otherwise fail later with an obscure SQL error in the middle
    of a payment. There is no migration tool yet; for demo data the fix is to
    delete the file. A pilot database should get Alembic before its first change.
    """
    insp = inspect(engine)
    missing = []
    for table in SQLModel.metadata.sorted_tables:
        have = {c["name"] for c in insp.get_columns(table.name)}
        missing += [f"{table.name}.{c.name}" for c in table.columns if c.name not in have]
    if missing:
        raise RuntimeError(
            "Database schema is older than the code (missing: "
            + ", ".join(missing[:8])
            + "). For demo data, delete the database file and restart."
        )


def get_session() -> Iterator[Session]:
    # expire_on_commit=False keeps attributes readable after commit so handlers
    # can serialize an object without a re-fetch.
    with Session(engine, expire_on_commit=False) as session:
        yield session
