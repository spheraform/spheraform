"""Dataset model - unified catalogue of discovered datasets."""

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
from sqlalchemy.orm import Mapped, mapped_column, relationship, deferred
from geoalchemy2 import Geometry
import enum

from .base import Base, TimestampMixin, UUIDMixin, ArrayOfText


class DownloadStrategy(str, enum.Enum):
    """Download strategy based on dataset size."""

    SIMPLE = "simple"  # < server limit, single request
    PAGED = "paged"  # 10K-100K features, sequential paging
    CHUNKED = "chunked"  # 100K-1M features, parallel chunks
    DISTRIBUTED = "distributed"  # > 1M features, background job queue


class Dataset(Base, UUIDMixin, TimestampMixin):
    """
    Unified catalogue of all discovered datasets.

    Each dataset represents a layer/feature service from a geoserver.
    """

    __tablename__ = "datasets"

    # Foreign key to geoserver
    geoserver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("geoservers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Basic metadata
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Search and classification
    keywords: Mapped[Optional[list[str]]] = mapped_column(ArrayOfText(), nullable=True)
    themes: Mapped[Optional[list[str]]] = mapped_column(
        ArrayOfText(), nullable=True, index=True
    )
    # Themes: hydro, transport, admin, boundaries, elevation, imagery, etc.

    # Spatial extent (for spatial search)
    # Deferred loading to avoid loading large geometry data by default
    bbox: Mapped[Optional[str]] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326),
        deferred=True,
        nullable=True,
    )

    # Dataset characteristics
    feature_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_date: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    download_formats: Mapped[Optional[list[str]]] = mapped_column(
        ArrayOfText(), nullable=True
    )
    access_url: Mapped[str] = mapped_column(Text, nullable=False)

    # Enriched metadata
    service_item_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )  # True unique identifier for ArcGIS datasets
    geometry_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True
    )  # Point, LineString, Polygon, etc.
    source_srid: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # Source coordinate system (EPSG/WKID)
    max_record_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # Maximum records per request (pagination limit)
    last_edit_date: Mapped[Optional[datetime]] = mapped_column(
        nullable=True
    )  # Last edit date from source
    last_fetched_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True
    )  # When dataset was last fetched/cached (distinct from crawl)

    # Change Detection
    cached_etag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cached_last_modified: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_change_check: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    change_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Cache Status
    is_cached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cached_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    cache_table: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )  # PostGIS table name if cached (DEPRECATED - for backward compatibility)
    cache_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # S3 Storage (GeoParquet + PMTiles)
    storage_format: Mapped[str] = mapped_column(
        SQLEnum("postgis", "geoparquet", "hybrid", name="storage_format"),
        default="postgis",
        nullable=False,
        index=True,
    )
    use_s3_storage: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    s3_data_key: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # Path to GeoParquet file in S3
    s3_tiles_key: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # Path to PMTiles file in S3
    parquet_schema: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON schema of GeoParquet
    parquet_row_groups: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # Number of row groups in Parquet file

    # PMTiles Generation Tracking
    pmtiles_generated: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    pmtiles_generated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    pmtiles_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Download Strategy
    download_strategy: Mapped[DownloadStrategy] = mapped_column(
        SQLEnum(DownloadStrategy, name="download_strategy", values_callable=lambda x: [e.value for e in x]),
        default=DownloadStrategy.SIMPLE,
        nullable=False,
    )

    # Quality metrics
    quality_score: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # 0-100
    has_geometry_errors: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    last_validated: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # License and attribution
    license: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attribution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    # If dataset disappears from server during crawl, mark as inactive

    # Additional metadata from source
    source_metadata: Mapped[Optional[dict]] = mapped_column(
        Text, nullable=True
    )  # Store raw metadata JSON as text

    # Relationships
    # geoserver = relationship("Geoserver", back_populates="datasets")

    def __repr__(self) -> str:
        return f"<Dataset(name='{self.name}', external_id='{self.external_id}', features={self.feature_count})>"


# Create composite index for common queries
Index(
    "ix_datasets_geoserver_active",
    Dataset.geoserver_id,
    Dataset.is_active,
)

Index(
    "ix_datasets_themes_active",
    Dataset.themes,
    Dataset.is_active,
    postgresql_using="gin",  # GIN index for array searches
)

# Spatial index on bbox
Index(
    "ix_datasets_bbox",
    Dataset.bbox,
    postgresql_using="gist",
)
