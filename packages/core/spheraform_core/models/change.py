"""Change detection models - tracking dataset change probes."""

from datetime import datetime
from typing import Optional
import uuid
from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    ForeignKey,
    Enum as SQLEnum,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
import enum

from .base import Base, UUIDMixin


class ChangeCheckMethod(str, enum.Enum):
    """Method used to check for changes."""

    ETAG = "etag"  # HTTP ETag header
    LAST_MODIFIED = "last_modified"  # HTTP Last-Modified header
    ARCGIS_EDIT_DATE = "arcgis_edit_date"  # ArcGIS editingInfo.lastEditDate
    WFS_UPDATE_SEQUENCE = "wfs_update_sequence"  # WFS updateSequence
    CKAN_MODIFIED = "ckan_modified"  # CKAN metadata_modified
    FEATURE_COUNT = "feature_count"  # Compare feature counts
    SAMPLE_CHECKSUM = "sample_checksum"  # Checksum of sample features
    METADATA_HASH = "metadata_hash"  # Hash of metadata


class ChangeCheck(Base, UUIDMixin):
    """
    History of change detection probes.

    Logs every time we check if a dataset has changed.
    Used for debugging and analytics.
    """

    __tablename__ = "change_checks"

    # Foreign key to dataset
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # When checked
    checked_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    # What method was used
    method: Mapped[ChangeCheckMethod] = mapped_column(
        SQLEnum(ChangeCheckMethod, name="change_check_method", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # Results
    changed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    conclusive: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )  # Was the check definitive?

    # Performance metrics
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Did this check trigger a download?
    triggered_download: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Additional details
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON string with method-specific details:
    # {"old_etag": "...", "new_etag": "...", "changed": true}
    # {"old_count": 1000, "new_count": 1050, "changed": true}

    # Error information
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ChangeCheck(dataset_id={self.dataset_id}, method='{self.method}', changed={self.changed})>"


# Index for querying change history
Index(
    "ix_change_checks_dataset_checked",
    ChangeCheck.dataset_id,
    ChangeCheck.checked_at.desc(),
)
