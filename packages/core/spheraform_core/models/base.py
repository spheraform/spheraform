"""Base SQLAlchemy model and database setup."""

from datetime import datetime
from typing import Any
from sqlalchemy import DateTime, MetaData, JSON, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import uuid
import json


# Cross-database compatible types
# These use PostgreSQL-specific types when available, fall back to JSON for SQLite

# JSON/JSONB type that works with both PostgreSQL and SQLite
JSONType = JSON().with_variant(JSONB(), "postgresql")


# Text array type - uses ARRAY for PostgreSQL, JSON for SQLite
class ArrayOfText(TypeDecorator):
    """Array of text that works with both PostgreSQL and SQLite."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Text))
        else:
            return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        else:
            # For SQLite, store as JSON
            return value

    def process_result_value(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        else:
            # For SQLite, return the JSON-decoded value
            return value


# UUID array type - uses ARRAY for PostgreSQL, JSON for SQLite
class ArrayOfUUID(TypeDecorator):
    """Array of UUIDs that works with both PostgreSQL and SQLite."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(PGUUID(as_uuid=True)))
        else:
            return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        else:
            # For SQLite, convert UUIDs to strings for JSON storage
            if value is not None:
                return [str(v) for v in value]
            return value

    def process_result_value(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        else:
            # For SQLite, convert strings back to UUIDs
            if value is not None:
                return [uuid.UUID(v) for v in value]
            return value


# PostgreSQL naming convention for constraints
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    """Base class for all database models."""

    metadata = metadata

    # Type annotation overrides for common column types
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class UUIDMixin:
    """Mixin for UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
