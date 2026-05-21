from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base


@lru_cache(maxsize=1)
def build_engine(echo: bool = False):
    settings = get_settings()
    # pool_pre_ping: validates connections before checkout so zombie connections
    # (left idle in transaction by crashed scripts, killed Python processes,
    # or PG restarts) are detected and replaced instead of returning stale
    # snapshots. pool_recycle keeps connections under 5 minutes old, well below
    # PostgreSQL's typical idle_in_transaction_session_timeout.
    return create_engine(
        settings.database_url,
        future=True,
        echo=echo,
        pool_pre_ping=True,
        pool_recycle=300,
    )


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(
        bind=build_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def init_db() -> None:
    engine = build_engine()
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Session:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
