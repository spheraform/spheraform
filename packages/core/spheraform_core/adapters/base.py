"""Base adapter interface for geoserver providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, AsyncIterator
from enum import Enum
import uuid


class ChangeCheckResult(str, Enum):
    """Result of a change check."""

    CHANGED = "changed"  # Definitive change detected
    UNCHANGED = "unchanged"  # Definitive no change
    INCONCLUSIVE = "inconclusive"  # Cannot determine


@dataclass
class ServerCapabilities:
    """
    Discovered capabilities of a geoserver.

    Probed during initial setup to understand server limits.
    """

    max_features_per_request: int = 1000
    supports_pagination: bool = True
    supports_result_offset: bool = True
    supports_oid_query: bool = False
    oid_field_name: Optional[str] = None
    supports_bbox_filter: bool = True
    supports_spatial_filter: bool = True
    output_formats: list[str] = None

    def __post_init__(self):
        if self.output_formats is None:
            self.output_formats = ["geojson"]


@dataclass
class DatasetMetadata:
    """
    Normalized metadata for a dataset.

    Adapters convert provider-specific metadata to this common format.
    """

    external_id: str
    name: str
    access_url: str
    description: Optional[str] = None
    keywords: Optional[list[str]] = None
    bbox: Optional[tuple[float, float, float, float]] = None  # (minx, miny, maxx, maxy)
    feature_count: Optional[int] = None
    updated_date: Optional[datetime] = None
    download_formats: Optional[list[str]] = None
    license: Optional[str] = None
    attribution: Optional[str] = None
    source_metadata: Optional[dict] = None  # Raw metadata from source

    # Enriched metadata fields
    service_item_id: Optional[str] = None  # True unique identifier (e.g., ArcGIS serviceItemId)
    geometry_type: Optional[str] = None  # Point, LineString, Polygon, etc.
    source_srid: Optional[int] = None  # Source coordinate system (EPSG/WKID)
    last_edit_date: Optional[datetime] = None  # Last edit date from source
    themes: Optional[list[str]] = None  # Classified themes
    max_record_count: Optional[int] = None  # Maximum records per request (pagination limit)


@dataclass
class ChangeCheckInfo:
    """Information about a change check."""

    result: ChangeCheckResult
    method: str  # e.g., "etag", "last_modified", "arcgis_edit_date"
    changed: bool
    conclusive: bool
    details: Optional[dict] = None
    response_time_ms: Optional[int] = None
    error: Optional[str] = None


@dataclass
class DownloadResult:
    """Result of a download operation."""

    success: bool
    output_path: Optional[str] = None
    feature_count: Optional[int] = None
    size_bytes: Optional[int] = None
    error: Optional[str] = None
    duration_seconds: Optional[float] = None


class BaseGeoserverAdapter(ABC):
    """
    Base class for all geoserver adapters.

    Each provider type (ArcGIS, WFS, CKAN, etc.) implements this interface.
    """

    # Provider type identifier
    provider_type: str = "base"

    def __init__(
        self,
        base_url: str,
        auth_config: Optional[dict] = None,
        connection_config: Optional[dict] = None,
        **kwargs
    ):
        """
        Initialize adapter.

        Args:
            base_url: Base URL of the geoserver
            auth_config: Authentication configuration
            connection_config: Connection settings (timeout, retries, etc.)
            **kwargs: Provider-specific additional parameters
        """
        self.base_url = base_url.rstrip("/")
        self.auth_config = auth_config or {}
        self.connection_config = connection_config or {}

        # Default connection settings
        self.timeout = self.connection_config.get("timeout", 60)
        self.max_retries = self.connection_config.get("max_retries", 3)
        self.verify_ssl = self.connection_config.get("verify_ssl", True)

    # --- Setup and Probing ---

    @abstractmethod
    async def probe_capabilities(self) -> ServerCapabilities:
        """
        Probe server to discover capabilities.

        Called once during initial setup to understand server limits.

        Returns:
            ServerCapabilities object with discovered limits
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Quick health check of the server.

        Returns:
            True if server is healthy, False otherwise
        """
        pass

    # --- Discovery ---

    @abstractmethod
    async def discover_datasets(self) -> AsyncIterator[DatasetMetadata]:
        """
        Discover all datasets on the server.

        Called during crawl to build/update the catalogue.

        Yields:
            DatasetMetadata for each discovered dataset
        """
        pass

    # --- Change Detection ---

    @abstractmethod
    async def check_changed(
        self,
        dataset_id: uuid.UUID,
        external_id: str,
        cached_etag: Optional[str] = None,
        cached_last_modified: Optional[datetime] = None,
        source_updated_at: Optional[datetime] = None,
    ) -> ChangeCheckInfo:
        """
        Check if a dataset has changed (cheap check, no data download).

        Implementations should try methods in order of cost:
        1. HTTP HEAD for ETag/Last-Modified
        2. Provider-specific metadata (ArcGIS editingInfo, WFS updateSequence)
        3. Feature count comparison
        4. Sample checksum (most expensive)

        Args:
            dataset_id: Internal dataset UUID
            external_id: Provider's dataset ID
            cached_etag: Previously cached ETag
            cached_last_modified: Previously cached Last-Modified timestamp
            source_updated_at: Previously cached source update timestamp

        Returns:
            ChangeCheckInfo with result and details
        """
        pass

    # --- Downloads ---

    @abstractmethod
    async def download_simple(
        self,
        external_id: str,
        output_path: str,
        geometry: Optional[dict] = None,
        format: str = "geojson",
    ) -> DownloadResult:
        """
        Download dataset in a single request.

        Use for small datasets that fit within server limits.

        Args:
            external_id: Provider's dataset ID
            output_path: Where to save the downloaded data
            geometry: Optional GeoJSON geometry to clip/filter
            format: Output format (default: geojson)

        Returns:
            DownloadResult with success status and details
        """
        pass

    @abstractmethod
    async def download_paged(
        self,
        external_id: str,
        output_path: str,
        geometry: Optional[dict] = None,
        format: str = "geojson",
    ) -> DownloadResult:
        """
        Download dataset using sequential pagination.

        Use for medium datasets (10K-100K features).

        Args:
            external_id: Provider's dataset ID
            output_path: Where to save the downloaded data
            geometry: Optional GeoJSON geometry to clip/filter
            format: Output format (default: geojson)

        Returns:
            DownloadResult with success status and details
        """
        pass

    # --- Metadata Queries ---

    @abstractmethod
    async def get_feature_count(self, external_id: str) -> Optional[int]:
        """
        Get the number of features in a dataset.

        Args:
            external_id: Provider's dataset ID

        Returns:
            Feature count, or None if unavailable
        """
        pass

    # --- Provider-Specific Methods (optional, override if supported) ---

    async def get_oid_range(self, external_id: str) -> Optional[tuple[int, int]]:
        """
        Get OID range for a dataset (ArcGIS-specific).

        Returns:
            (min_oid, max_oid) tuple, or None if not supported
        """
        return None

    async def fetch_by_oid_range(
        self,
        external_id: str,
        min_oid: int,
        max_oid: int,
        output_path: str,
    ) -> DownloadResult:
        """
        Fetch features within OID range (ArcGIS parallel download).

        Args:
            external_id: Provider's dataset ID
            min_oid: Minimum OBJECTID
            max_oid: Maximum OBJECTID
            output_path: Where to save the chunk

        Returns:
            DownloadResult with success status
        """
        raise NotImplementedError(
            f"{self.provider_type} does not support OID range queries"
        )

    async def fetch_by_bbox(
        self,
        external_id: str,
        bbox: tuple[float, float, float, float],
        output_path: str,
    ) -> DownloadResult:
        """
        Fetch features within bounding box (spatial chunk download).

        Args:
            external_id: Provider's dataset ID
            bbox: (minx, miny, maxx, maxy)
            output_path: Where to save the chunk

        Returns:
            DownloadResult with success status
        """
        raise NotImplementedError(
            f"{self.provider_type} does not support bbox queries"
        )

    # --- Utility Methods ---

    def _build_auth_headers(self) -> dict:
        """
        Build authentication headers from auth_config.

        Override in subclasses for provider-specific auth.
        """
        headers = {}

        if self.auth_config.get("type") == "api_key":
            key_name = self.auth_config.get("key_name", "X-API-Key")
            headers[key_name] = self.auth_config.get("key")

        elif self.auth_config.get("type") == "bearer":
            headers["Authorization"] = f"Bearer {self.auth_config.get('token')}"

        return headers
