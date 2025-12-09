"""SQLAlchemy models for geodata aggregator."""

from .base import Base, TimestampMixin, UUIDMixin
from .geoserver import Geoserver, ProviderType, HealthStatus
from .dataset import Dataset, DownloadStrategy
from .change import ChangeCheck, ChangeCheckMethod
from .job import (
    DownloadJob,
    DownloadChunk,
    ExportJob,
    CrawlJob,
    JobStatus,
    ExportFormat,
)
from .theme import Theme

__all__ = [
    # Base
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    # Geoserver
    "Geoserver",
    "ProviderType",
    "HealthStatus",
    # Dataset
    "Dataset",
    "DownloadStrategy",
    # Change detection
    "ChangeCheck",
    "ChangeCheckMethod",
    # Jobs
    "DownloadJob",
    "DownloadChunk",
    "ExportJob",
    "CrawlJob",
    "JobStatus",
    "ExportFormat",
    # Taxonomy
    "Theme",
]
