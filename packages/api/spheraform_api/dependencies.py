"""FastAPI dependencies."""

from typing import Generator
from sqlalchemy.orm import Session

from spheraform_core.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Get database session.

    Yields database session and ensures it's closed after request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
