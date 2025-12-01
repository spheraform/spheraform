"""Geoserver adapter implementations."""

from .base import (
    BaseGeoserverAdapter,
    ServerCapabilities,
    DatasetMetadata,
    ChangeCheckInfo,
    ChangeCheckResult,
    DownloadResult,
)
from .arcgis import ArcGISAdapter

__all__ = [
    "BaseGeoserverAdapter",
    "ServerCapabilities",
    "DatasetMetadata",
    "ChangeCheckInfo",
    "ChangeCheckResult",
    "DownloadResult",
    "ArcGISAdapter",
]
