"""Database connection and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator

from .config import settings
from .models.base import Base

# Create engine
engine = create_engine(
    str(settings.database_url),
    echo=False,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,
    max_overflow=20,
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Get a database session.

    Usage:
        with get_db() as db:
            db.query(Model).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize database tables.

    Only use for development/testing. In production, use Alembic migrations.
    """
    Base.metadata.create_all(bind=engine)
