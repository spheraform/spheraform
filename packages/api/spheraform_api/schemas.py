"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Optional, List, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator
from geoalchemy2.shape import to_shape

from spheraform_core.models import ProviderType, HealthStatus, DownloadStrategy


# --- Server Schemas ---

class ServerCreate(BaseModel):
    """Schema for creating a geoserver."""

    name: str = Field(..., description="Human-readable name")
    base_url: str = Field(..., description="Base URL of the geoserver")
    provider_type: ProviderType = Field(..., description="Provider type")
    auth_config: Optional[dict] = Field(None, description="Authentication configuration")
    connection_config: Optional[dict] = Field(None, description="Connection configuration")
    probe_frequency_hours: int = Field(24, description="Hours between change probes")
    description: Optional[str] = None
    contact_email: Optional[str] = None
    organization: Optional[str] = None
    country: Optional[str] = Field(None, description="ISO 3166-1 alpha-2 country code(s), comma-separated (e.g. GB or BE,NL,LU)", max_length=50)


class ServerUpdate(BaseModel):
    """Schema for updating a geoserver."""

    name: Optional[str] = None
    base_url: Optional[str] = None
    auth_config: Optional[dict] = None
    connection_config: Optional[dict] = None
    probe_frequency_hours: Optional[int] = None
    description: Optional[str] = None
    contact_email: Optional[str] = None
    organization: Optional[str] = None
    country: Optional[str] = Field(None, max_length=50)


class ServerResponse(BaseModel):
    """Schema for geoserver response."""

    id: UUID
    name: str
    base_url: str
    provider_type: ProviderType
    health_status: HealthStatus
    last_crawl: Optional[datetime]
    probe_frequency_hours: int
    dataset_count: int
    active_dataset_count: int
    description: Optional[str]
    contact_email: Optional[str]
    organization: Optional[str]
    country: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Dataset Schemas ---

class DatasetResponse(BaseModel):
    """Schema for dataset response."""

    id: UUID
    geoserver_id: UUID
    external_id: str
    name: str
    description: Optional[str]
    keywords: Optional[List[str]]
    themes: Optional[List[str]]
    bbox: Optional[str] = None  # WKT POLYGON geometry
    feature_count: Optional[int]
    updated_date: Optional[datetime]
    download_formats: Optional[List[str]]
    access_url: str
    is_cached: bool
    cached_at: Optional[datetime]
    cache_table: Optional[str]
    download_strategy: DownloadStrategy
    quality_score: Optional[int]
    license: Optional[str]
    attribution: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Enriched metadata
    service_item_id: Optional[str] = None
    geometry_type: Optional[str] = None
    source_srid: Optional[int] = None
    last_edit_date: Optional[datetime] = None
    last_fetched_at: Optional[datetime] = None

    # Storage metadata
    storage_format: Optional[str] = None
    use_s3_storage: bool = False
    s3_data_key: Optional[str] = None
    s3_tiles_key: Optional[str] = None
    pmtiles_generated: bool = False
    pmtiles_generated_at: Optional[datetime] = None
    pmtiles_size_bytes: Optional[int] = None
    pmtiles_url: Optional[str] = None

    @field_validator('bbox', mode='before')
    @classmethod
    def convert_bbox_to_wkt(cls, value: Any) -> Optional[str]:
        """Convert bbox WKBElement to WKT string before validation."""
        if value is None:
            return None
        try:
            # Convert GeoAlchemy2 WKBElement to Shapely geometry, then to WKT
            shape = to_shape(value)
            return shape.wkt
        except Exception:
            # If conversion fails, return None
            return None

    @model_validator(mode='after')
    def add_pmtiles_url(self) -> 'DatasetResponse':
        """Add PMTiles URL if tiles are available."""
        if self.s3_tiles_key:
            from spheraform_core.storage.s3_client import S3Client
            s3_client = S3Client()
            self.pmtiles_url = s3_client.get_public_url(self.s3_tiles_key)
        return self

    class Config:
        from_attributes = True


# --- Search Schemas ---

class SearchRequest(BaseModel):
    """Schema for search request."""

    geometry: Optional[dict] = Field(None, description="GeoJSON geometry to search within")
    point: Optional[List[float]] = Field(None, description="[lon, lat] point")
    buffer_km: Optional[float] = Field(None, description="Buffer distance in kilometers")
    text: Optional[str] = Field(None, description="Full-text search")
    themes: Optional[List[str]] = Field(None, description="Filter by themes")
    formats: Optional[List[str]] = Field(None, description="Filter by formats")
    providers: Optional[List[str]] = Field(None, description="Filter by providers")
    updated_after: Optional[datetime] = Field(None, description="Updated after date")
    cached_only: bool = Field(False, description="Only return cached datasets")
    limit: int = Field(50, ge=1, le=1000, description="Results per page")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class SearchResponse(BaseModel):
    """Schema for search response."""

    total: int
    datasets: List[DatasetResponse]
    facets: dict = Field(default_factory=dict, description="Facets for filtering")


# --- Download Schemas ---

class DownloadRequest(BaseModel):
    """Schema for download request."""

    dataset_ids: List[UUID] = Field(..., description="Dataset IDs to download")
    geometry: Optional[dict] = Field(None, description="GeoJSON geometry to clip")
    format: str = Field("geojson", description="Output format")
    crs: Optional[str] = Field(None, description="Target CRS (e.g., EPSG:4326)")
    merge: bool = Field(False, description="Merge into single file")
    force_refresh: bool = Field(False, description="Force re-fetch even if cached")


class DownloadResponse(BaseModel):
    """Schema for download response."""

    job_id: Optional[UUID] = None
    download_url: Optional[str] = None
    status: str


# --- Job Schemas ---

class JobStatusResponse(BaseModel):
    """Schema for job status response."""

    id: UUID
    status: str
    progress: Optional[float] = None
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error: Optional[str]
    output_path: Optional[str]

    class Config:
        from_attributes = True


class CrawlJobResponse(BaseModel):
    """Schema for crawl job status response."""

    id: UUID
    geoserver_id: UUID
    status: str
    progress: Optional[float] = None  # 0-100
    total_services: Optional[int] = None
    services_processed: int
    datasets_discovered: int
    datasets_new: int
    datasets_updated: int
    current_stage: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True


class DownloadJobProgressResponse(BaseModel):
    """Enhanced schema for download job with detailed progress information."""

    id: UUID
    dataset_id: UUID
    status: str
    progress: Optional[float] = None  # 0-100
    current_stage: Optional[str] = None
    total_features: Optional[int] = None
    features_downloaded: int
    features_stored: int
    chunks_completed: int
    total_chunks: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    output_path: Optional[str] = None

    class Config:
        from_attributes = True
