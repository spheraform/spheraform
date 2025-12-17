"""Utilities for Celery task execution."""

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from spheraform_core.config import settings

# Thread-safe session factory for workers
# Each worker process gets its own connection pool
# Use psycopg (v3) driver explicitly since psycopg2 is not installed
database_url = settings.database_url
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql+psycopg2://"):
    database_url = database_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)

engine = create_engine(
    database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Validate connections before using
)
SessionLocal = scoped_session(sessionmaker(bind=engine))


@contextmanager
def get_db_session():
    """
    Thread-safe database session for Celery tasks.

    Usage:
        with get_db_session() as db:
            dataset = db.query(Dataset).first()
            db.commit()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
