"""
Synchronous Database Access for BeatStitch Worker

The worker uses synchronous database operations since RQ tasks are sync.
This module provides a sync session factory and context manager.
"""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase


# Get database URL from environment (convert async URL to sync if needed)
def get_database_url() -> str:
    """
    Get database URL from environment variable.
    Converts async SQLite URL to sync URL if needed.
    """
    url = os.environ.get("DATABASE_URL", "sqlite:////data/db/beatstitch.db")

    # Convert async SQLite URL to sync URL
    if url.startswith("sqlite+aiosqlite://"):
        url = url.replace("sqlite+aiosqlite://", "sqlite://")

    return url


# Create sync engine
_engine = None


def get_engine():
    """Get or create the sync database engine."""
    global _engine
    if _engine is None:
        database_url = get_database_url()
        _engine = create_engine(
            database_url,
            echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
        )
    return _engine


# Session factory
_SessionLocal = None


def get_session_factory():
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
        )
    return _SessionLocal


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager that provides a database session.

    Usage:
        with get_db_session() as db:
            audio = db.query(AudioTrack).filter_by(id=audio_id).first()
            audio.analysis_status = "processing"
            db.commit()
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Base class for models (for type hints only - actual models come from backend)
class Base(DeclarativeBase):
    """Base class for SQLAlchemy models (for type hints)."""
    pass
