from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.schemas.editorial_export import EditorialExportPolicy


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def build_settings(**overrides) -> Settings:
    payload = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "timezone": "Europe/Madrid",
        "app_root": Path.cwd(),
    }
    payload.update(overrides)
    return Settings(**payload)


def build_export_policy(**overrides) -> EditorialExportPolicy:
    payload = {
        "use_rewrite_by_default": True,
        "max_text_length": 240,
        "duplicate_window_hours": 72,
        "max_line_breaks": 6,
    }
    payload.update(overrides)
    return EditorialExportPolicy(**payload)
