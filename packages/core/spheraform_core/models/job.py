"""Job models - background jobs for downloads and exports."""

from datetime import datetime
from typing import Optional
import uuid
from sqlalchemy import (
    String,
    Text,
    Integer,
    ForeignKey,
    Enum as SQLEnum,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry
import enum

from .base import Base, TimestampMixin, UUIDMixin


class JobStatus(str, enum.Enum):
    """Status of a background job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExportFormat(str, enum.Enum):
    """Export format options."""

    GEOJSON = "geojson"
    GEOPACKAGE = "gpkg"
    SHAPEFILE = "shp"
    MBTILES = "mbtiles"
    PMTILES = "pmtiles"
    POSTGIS = "postgis"
    GEOPARQUET = "geoparquet"
    CSV_WKT = "csv"
    KML = "kml"
    FLATGEOBUF = "fgb"


class DownloadJob(Base, UUIDMixin, TimestampMixin):
    """
    Background download jobs for large datasets.

    Tracks progress of multi-chunk downloads.
    """

    __tablename__ = "download_jobs"

    # Dataset being downloaded
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Job status
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus, name="job_status"),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Download strategy
    strategy: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # simple, paged, chunked

    # Progress tracking (for chunked downloads)
    total_chunks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chunks_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Output
    output_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_format: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Error tracking
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Additional parameters
    params: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Example params: {"clip_geometry": {...}, "crs": "EPSG:4326"}

    def __repr__(self) -> str:
        return f"<DownloadJob(dataset_id={self.dataset_id}, status='{self.status}', progress={self.chunks_completed}/{self.total_chunks})>"


class DownloadChunk(Base, UUIDMixin):
    """
    Individual chunks for resumable large downloads.

    Each chunk represents a portion of a large dataset.
    """

    __tablename__ = "download_chunks"

    # Parent job
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("download_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Chunk order
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Download strategy for this chunk
    strategy: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # oid_range, offset, spatial_grid

    # Parameters for fetching this chunk
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Example params by strategy:
    # oid_range: {"min_oid": 0, "max_oid": 1000}
    # offset: {"offset": 5000, "limit": 1000}
    # spatial_grid: {"bbox": [x1, y1, x2, y2]}

    # Status
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus, name="job_status"),
        default=JobStatus.PENDING,
        nullable=False,
    )

    # Output
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feature_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Error tracking
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<DownloadChunk(job_id={self.job_id}, index={self.chunk_index}, status='{self.status}')>"


Index(
    "ix_download_chunks_job_status",
    DownloadChunk.job_id,
    DownloadChunk.status,
)


class ExportJob(Base, UUIDMixin, TimestampMixin):
    """
    User-requested exports (MBTiles, PostGIS, etc.).

    Tracks export jobs that convert/load data to various formats.
    """

    __tablename__ = "export_jobs"

    # Datasets to export
    dataset_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False
    )

    # Export format
    format: Mapped[ExportFormat] = mapped_column(
        SQLEnum(ExportFormat, name="export_format"),
        nullable=False,
    )

    # Optional clip geometry
    clip_geometry: Mapped[Optional[str]] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326),
        nullable=True,
    )

    # Job status
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus, name="job_status"),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Output
    output_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Expiration (for cleanup)
    expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True, index=True)

    # Error tracking
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Format-specific parameters
    params: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Example for PostGIS: {"connection_string": "...", "schema": "imported"}
    # Example for MBTiles: {"min_zoom": 0, "max_zoom": 14, "bounds": [...]}

    # User tracking (optional)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<ExportJob(format='{self.format}', status='{self.status}', datasets={len(self.dataset_ids)})>"
