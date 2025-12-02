"""Geoserver model - represents remote servers we pull data from."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from .base import Base, TimestampMixin, UUIDMixin, JSONType


class ProviderType(str, enum.Enum):
    """Supported geoserver provider types."""

    ARCGIS = "arcgis"
    WFS = "wfs"
    WCS = "wcs"
    CKAN = "ckan"
    GEOSERVER = "geoserver"
    S3 = "s3"
    ATOM = "atom"
    OPENDATASOFT = "opendatasoft"
    DIRECT = "direct"
    GEE = "gee"  # Google Earth Engine


class HealthStatus(str, enum.Enum):
    """Health status of a geoserver."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class Geoserver(Base, UUIDMixin, TimestampMixin):
    """
    Registered remote servers we pull data from.

    Stores connection information, capabilities, and health status.
    """

    __tablename__ = "geoservers"

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    provider_type: Mapped[ProviderType] = mapped_column(
        SQLEnum(ProviderType, name="provider_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # Authentication (encrypted credentials stored as JSON)
    auth_config: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)

    # Server capabilities (discovered during probe)
    capabilities: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    # Example capabilities structure:
    # {
    #   "max_features_per_request": 1000,
    #   "supports_pagination": true,
    #   "supports_result_offset": true,
    #   "supports_oid_query": true,
    #   "oid_field_name": "OBJECTID",
    #   "supports_bbox_filter": true,
    #   "output_formats": ["geojson", "json", "pbf"]
    # }

    # Health and status
    health_status: Mapped[HealthStatus] = mapped_column(
        SQLEnum(HealthStatus, name="health_status", values_callable=lambda x: [e.value for e in x]),
        default=HealthStatus.UNKNOWN,
        nullable=False,
    )
    last_crawl: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Configuration
    probe_frequency_hours: Mapped[int] = mapped_column(
        Integer,
        default=24,
        nullable=False,
    )
    rate_limit_config: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    # Example rate_limit_config:
    # {
    #   "requests_per_second": 5,
    #   "burst": 10,
    #   "backoff_seconds": 60
    # }

    # Connection configuration
    connection_config: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    # Example connection_config:
    # {
    #   "timeout": 60,
    #   "max_retries": 3,
    #   "verify_ssl": true,
    #   "custom_headers": {}
    # }

    # Statistics (denormalized for performance)
    dataset_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_dataset_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    organization: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<Geoserver(name='{self.name}', type='{self.provider_type}', status='{self.health_status}')>"
