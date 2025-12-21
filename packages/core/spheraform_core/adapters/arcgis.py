"""ArcGIS REST API adapter."""

import asyncio
import logging
from datetime import datetime
from typing import AsyncIterator, Optional, Dict, Callable
import uuid
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import (
    BaseGeoserverAdapter,
    ServerCapabilities,
    DatasetMetadata,
    ChangeCheckInfo,
    ChangeCheckResult,
    DownloadResult,
)
from ..proxy import proxy_manager
from .theme_classifier import ThemeClassifier

logger = logging.getLogger("gunicorn.error")

class ArcGISAdapter(BaseGeoserverAdapter):
    """
    Adapter for ArcGIS REST API servers.

    Supports FeatureServers and MapServers with query capabilities.
    """

    provider_type = "arcgis"

    def __init__(
        self,
        base_url: str,
        connection_config: Optional[Dict] = None,
        country_hint: Optional[str] = None,
        **kwargs
    ):
        super().__init__(base_url, **kwargs)
        self.connection_config = connection_config or {}
        self.country_hint = country_hint

        # Use browser-like headers to avoid WAF blocking
        # Note: Do NOT include "br" (brotli) in Accept-Encoding unless brotli is installed
        # httpx will not auto-decompress brotli responses without the brotli library
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        }

        # Get proxy configuration
        proxy_url = proxy_manager.get_proxy_for_server(
            self.connection_config, self.country_hint
        )

        # Log proxy usage
        if proxy_url:
            logger.info(f"ArcGIS adapter using proxy: {proxy_url} for {base_url}")
        else:
            logger.info(f"ArcGIS adapter NOT using proxy for {base_url}")

        # Create HTTP client with optional proxy
        client_kwargs = {
            "timeout": self.timeout,
            "verify": self.verify_ssl,
            "headers": headers,
            "follow_redirects": True,
        }

        if proxy_url:
            # httpx AsyncClient uses 'proxy' parameter with a URL string
            client_kwargs["proxy"] = proxy_url

        self.client = httpx.AsyncClient(**client_kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(5),  # Increased from 3 to 5 attempts
        wait=wait_exponential(min=1, max=10),
        reraise=True
    )
    async def _request(self, url: str, params: dict = None) -> dict:
        """
        Make HTTP request with retry logic.

        Retries on transient errors like network timeouts, 5xx server errors.
        Fails fast on 4xx client errors (except 429 rate limit).
        """
        import gzip
        import json

        headers = self._build_auth_headers()
        params = params or {}
        params.setdefault("f", "pjson")  # Use pjson for better compatibility with ArcGIS REST

        try:
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()

            # Get raw content bytes
            content = response.content

            # Check if content is gzipped and manually decompress if needed
            # Gzip files start with magic number 0x1f8b

            if content[:2] == b'\x1f\x8b':
                # Content is gzipped, decompress it
                content = gzip.decompress(content)

            # Decode and parse JSON
            return json.loads(content.decode('utf-8'))
        except httpx.HTTPStatusError as e:
            # Don't retry on 4xx client errors (except 429 Too Many Requests)
            if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200] if e.response.text else 'No response body'}"
                logger.error(f"Client error for {url}: {error_msg}")
                raise Exception(error_msg) from e
            # Retry on 5xx server errors and 429
            logger.warning(f"Retryable HTTP {e.response.status_code} for {url}, will retry")
            raise
        except httpx.TimeoutException as e:
            error_msg = f"Request timeout after {self.client.timeout}s"
            logger.warning(f"Timeout for {url}, will retry: {error_msg}")
            raise Exception(error_msg) from e
        except httpx.NetworkError as e:
            error_msg = f"Network error: {type(e).__name__} - {str(e) or 'Connection failed'}"
            logger.warning(f"Network error for {url}, will retry: {error_msg}")
            raise Exception(error_msg) from e
        except httpx.RemoteProtocolError as e:
            error_msg = f"Protocol error: {type(e).__name__} - {str(e) or 'Remote protocol error'}"
            logger.warning(f"Protocol error for {url}, will retry: {error_msg}")
            raise Exception(error_msg) from e
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response: {e.msg} at line {e.lineno}"
            logger.error(f"JSON decode error for {url}: {error_msg}")
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e) or 'Unknown error'}"
            logger.error(f"Unexpected error in _request for {url}: {error_msg}")
            raise Exception(error_msg) from e

    async def probe_capabilities(self) -> ServerCapabilities:
        """
        Probe ArcGIS server to discover capabilities.

        Checks a sample FeatureServer to understand pagination limits.
        """
        try:
            # Get server info
            info = await self._request(f"{self.base_url}/?f=json")

            # Default ArcGIS capabilities
            capabilities = ServerCapabilities(
                max_features_per_request=1000,  # Common ArcGIS default
                supports_pagination=True,
                supports_result_offset=True,
                supports_oid_query=True,
                oid_field_name="OBJECTID",  # Standard ArcGIS field
                supports_bbox_filter=True,
                supports_spatial_filter=True,
                output_formats=["geojson", "json"],
            )

            # Check if we can get actual max record count from a service
            if "services" in info:
                for service in info.get("services", [])[:1]:  # Check first service
                    service_name = service.get("name")
                    service_type = service.get("type")

                    if service_type == "FeatureServer":
                        service_url = f"{self.base_url}/{service_name}/FeatureServer"
                        service_info = await self._request(service_url)

                        if "maxRecordCount" in service_info:
                            capabilities.max_features_per_request = service_info[
                                "maxRecordCount"
                            ]
                        break

            return capabilities

        except Exception as e:
            # Return defaults if probing fails
            return ServerCapabilities()

    async def health_check(self) -> bool:
        """Quick health check of the ArcGIS server."""
        try:
            await self._request(self.base_url)
            return True
        except Exception:
            return False

    async def discover_datasets(self) -> AsyncIterator[DatasetMetadata]:
        """
        Discover all datasets (layers) from ArcGIS server.

        Walks through all folders and services to find FeatureServers.
        """
        try:
            # Get root catalog
            catalog = await self._request(self.base_url)

            # Log summary at INFO level
            services_count = len(catalog.get('services', []))
            folders_count = len(catalog.get('folders', []))
            logger.info(f"Starting discovery: {services_count} root services, {folders_count} folders")

            # Process services at root level
            for service in catalog.get("services", []):
                async for dataset in self._process_service(service):
                    yield dataset

            # Process folders
            for folder in catalog.get("folders", []):
                folder_url = f"{self.base_url}/{folder}"
                folder_catalog = await self._request(folder_url)

                for service in folder_catalog.get("services", []):
                    async for dataset in self._process_service(service):
                        yield dataset

        except Exception as e:
            # Log error but don't fail completely
            logger.exception(f"Error discovering datasets: {e}")

    async def _process_service(self, service: dict) -> AsyncIterator[DatasetMetadata]:
        """Process a single ArcGIS service and yield its layers."""
        service_name = service.get("name")
        service_type = service.get("type")

        # Only process FeatureServers (MapServers can also work but focus on Feature first)
        if service_type not in ["FeatureServer", "MapServer"]:
            return

        service_url = f"{self.base_url}/{service_name}/{service_type}"

        # Extract the map/service name (last part after any /)
        # e.g., "Public/EnvironmentConservation" -> "EnvironmentConservation"
        map_name = service_name.split('/')[-1] if service_name else "Unknown"

        try:
            service_info = await self._request(service_url)

            # Extract serviceItemId from service info (this is the true unique identifier)
            service_item_id = service_info.get("serviceItemId")

            # Process each layer in the service
            for layer in service_info.get("layers", []):
                layer_id = layer.get("id")
                layer_name = layer.get("name")

                # Get detailed layer information
                layer_url = f"{service_url}/{layer_id}"
                layer_info = await self._request(layer_url)

                # Get accurate feature count using returnCountOnly query
                feature_count = await self._get_feature_count(layer_url)

                # Extract metadata
                metadata = self._extract_metadata(
                    layer_info,
                    layer_url,
                    map_name,
                    service_item_id=service_item_id,
                    feature_count=feature_count
                )
                yield metadata

        except Exception as e:
            logger.exception(f"Error processing service {service_name}: {e}")

    async def _get_feature_count(self, layer_url: str) -> Optional[int]:
        """Get accurate feature count using returnCountOnly query."""
        try:
            query_url = f"{layer_url}/query"
            result = await self._request(query_url, params={
                "where": "1=1",
                "returnCountOnly": "true"
            })
            return result.get("count")
        except Exception as e:
            logger.warning(f"Could not get feature count for {layer_url}: {e}")
            return None

    def _extract_metadata(
        self,
        layer_info: dict,
        layer_url: str,
        map_name: str = None,
        service_item_id: Optional[str] = None,
        feature_count: Optional[int] = None
    ) -> DatasetMetadata:
        """Extract metadata from ArcGIS layer info."""
        # Extract source SRID/WKID first (needed for bbox transformation)
        source_srid = None
        if "extent" in layer_info and "spatialReference" in layer_info["extent"]:
            spatial_ref = layer_info["extent"]["spatialReference"]
            source_srid = spatial_ref.get("wkid") or spatial_ref.get("latestWkid")

        # Parse extent to bbox (in WGS84 for frontend compatibility)
        bbox = None
        if "extent" in layer_info:
            extent = layer_info["extent"]
            xmin = extent.get("xmin")
            ymin = extent.get("ymin")
            xmax = extent.get("xmax")
            ymax = extent.get("ymax")

            if all(v is not None for v in [xmin, ymin, xmax, ymax]):
                # Transform bbox to WGS84 (4326) if source SRID is different
                if source_srid and source_srid != 4326:
                    try:
                        from pyproj import Transformer
                        # Create transformer from source SRID to WGS84
                        transformer = Transformer.from_crs(
                            f"EPSG:{source_srid}",
                            "EPSG:4326",
                            always_xy=True
                        )
                        # Transform min and max corners
                        min_lon, min_lat = transformer.transform(xmin, ymin)
                        max_lon, max_lat = transformer.transform(xmax, ymax)
                        bbox = (min_lon, min_lat, max_lon, max_lat)
                    except Exception as e:
                        # If transformation fails, use original bbox
                        # (better than no bbox at all)
                        bbox = (xmin, ymin, xmax, ymax)
                        logger.warning(f"Failed to transform bbox from EPSG:{source_srid} to EPSG:4326: {e}")
                else:
                    # Already in WGS84 or no SRID info
                    bbox = (xmin, ymin, xmax, ymax)

        # Extract geometry type
        geometry_type = layer_info.get("geometryType")
        # Convert ArcGIS geometry type to standard format
        # e.g., "esriGeometryPoint" -> "Point"
        if geometry_type:
            geometry_type = geometry_type.replace("esriGeometry", "")

        # Extract keywords from description/tags
        keywords = []
        if "description" in layer_info:
            # Simple keyword extraction - can be improved
            keywords = layer_info["description"].split()[:10]

        # Combine map/service name with layer name for better clarity
        layer_name = layer_info.get("name", "Unnamed Layer")
        if map_name:
            # Combine map name and layer name with a hyphen
            dataset_name = f"{map_name} - {layer_name}"
        else:
            dataset_name = layer_name

        # Classify themes based on name and description
        themes = ThemeClassifier.classify(
            dataset_name,
            layer_info.get("description")
        )

        # Extract maxRecordCount for pagination
        max_record_count = layer_info.get("maxRecordCount")

        return DatasetMetadata(
            external_id=str(layer_info.get("id")),
            name=dataset_name,
            access_url=layer_url,
            description=layer_info.get("description"),
            keywords=keywords,
            bbox=bbox,
            feature_count=feature_count,
            updated_date=self._parse_edit_date(layer_info),
            download_formats=["geojson", "json"],
            license=None,  # ArcGIS doesn't standardize this
            attribution=layer_info.get("copyrightText"),
            source_metadata=layer_info,
            # Enriched metadata
            service_item_id=service_item_id,
            geometry_type=geometry_type,
            source_srid=source_srid,
            last_edit_date=self._parse_edit_date(layer_info),
            themes=themes,
            max_record_count=max_record_count,
        )

    def _parse_edit_date(self, layer_info: dict) -> Optional[datetime]:
        """Parse last edit date from ArcGIS layer info."""
        # Check editingInfo for lastEditDate (milliseconds since epoch)
        if "editingInfo" in layer_info:
            last_edit = layer_info["editingInfo"].get("lastEditDate")
            if last_edit:
                return datetime.fromtimestamp(last_edit / 1000)

        # Fallback to editFieldsInfo
        if "editFieldsInfo" in layer_info:
            # This tells us field names but not values
            pass

        return None

    async def check_changed(
        self,
        dataset_id: uuid.UUID,
        external_id: str,
        cached_etag: Optional[str] = None,
        cached_last_modified: Optional[datetime] = None,
        source_updated_at: Optional[datetime] = None,
    ) -> ChangeCheckInfo:
        """
        Check if dataset has changed using ArcGIS editingInfo.

        This is very efficient - just fetches layer metadata.
        """
        try:
            # Construct layer URL from external_id
            # external_id should be layer ID, need full URL
            # This is a simplification - in practice we'd store the full URL
            layer_url = f"{self.base_url}/FeatureServer/{external_id}"

            # Fetch layer info
            layer_info = await self._request(layer_url)

            # Get current edit date
            current_edit_date = self._parse_edit_date(layer_info)

            # Compare with cached date
            if source_updated_at and current_edit_date:
                changed = current_edit_date > source_updated_at
                return ChangeCheckInfo(
                    result=ChangeCheckResult.CHANGED if changed else ChangeCheckResult.UNCHANGED,
                    method="arcgis_edit_date",
                    changed=changed,
                    conclusive=True,
                    details={
                        "cached_date": source_updated_at.isoformat() if source_updated_at else None,
                        "current_date": current_edit_date.isoformat() if current_edit_date else None,
                    },
                )

            # If no cached date, assume changed
            if current_edit_date:
                return ChangeCheckInfo(
                    result=ChangeCheckResult.CHANGED,
                    method="arcgis_edit_date",
                    changed=True,
                    conclusive=True,
                    details={"current_date": current_edit_date.isoformat()},
                )

            # No edit date available - inconclusive
            return ChangeCheckInfo(
                result=ChangeCheckResult.INCONCLUSIVE,
                method="arcgis_edit_date",
                changed=False,
                conclusive=False,
            )

        except Exception as e:
            return ChangeCheckInfo(
                result=ChangeCheckResult.INCONCLUSIVE,
                method="arcgis_edit_date",
                changed=False,
                conclusive=False,
                error=str(e),
            )

    async def download_simple(
        self,
        external_id: str,
        output_path: str,
        geometry: Optional[dict] = None,
        format: str = "geojson",
    ) -> DownloadResult:
        """
        Download small dataset in a single request.

        Uses ArcGIS query endpoint with outFormat=geojson.
        """
        try:
            layer_url = f"{self.base_url}/FeatureServer/{external_id}/query"

            params = {
                "where": "1=1",  # Get all features
                "outFields": "*",  # Get all fields
                "returnGeometry": "true",
                "outSR": "4326",  # WGS84
                "f": "geojson" if format == "geojson" else "json",
            }

            # Add spatial filter if provided
            if geometry:
                # TODO: Convert GeoJSON geometry to ArcGIS geometry format
                pass

            # Use _request with retry logic instead of direct client call
            geojson = await self._request(layer_url, params=params)

            # Write to file
            import json
            with open(output_path, "w") as f:
                json.dump(geojson, f)

            import os
            size_bytes = os.path.getsize(output_path)

            # Count features
            feature_count = len(geojson.get("features", []))

            return DownloadResult(
                success=True,
                output_path=output_path,
                size_bytes=size_bytes,
                feature_count=feature_count,
            )

        except Exception as e:
            return DownloadResult(
                success=False,
                error=str(e),
            )

    async def download_paged(
        self,
        layer_url: str,
        output_path: str,
        max_records: Optional[int] = None,
        geometry: Optional[dict] = None,
        format: str = "geojson",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> DownloadResult:
        """
        Download dataset using offset-based pagination.

        For datasets larger than max_features_per_request.

        Args:
            layer_url: Full URL to the layer
            output_path: Path to save the GeoJSON file
            max_records: Maximum records per request (from dataset metadata, or will query if not provided)
            geometry: Optional spatial filter
            format: Output format (geojson)
            progress_callback: Optional callback(current, total) called periodically
        """
        try:
            query_url = f"{layer_url}/query"

            # Use provided max_records, or default to 1000
            page_size = max_records if max_records else 1000
            logger.info(f"Using page size {page_size} for download")

            # Get total count first
            count_params = {
                "where": "1=1",
                "returnCountOnly": "true",
                "f": "json",
            }
            count_result = await self._request(query_url, count_params)
            total_count = count_result.get("count", 0)

            if total_count == 0:
                # Empty dataset, write empty FeatureCollection
                import json
                with open(output_path, "w") as f:
                    json.dump({"type": "FeatureCollection", "features": []}, f)
                return DownloadResult(success=True, output_path=output_path, size_bytes=0, feature_count=0)

            # Stream write features to avoid memory issues with large datasets
            import json
            offset = 0
            feature_count = 0
            consecutive_connection_errors = 0

            # Open file and write GeoJSON header
            with open(output_path, "w") as f:
                f.write('{"type": "FeatureCollection", "features": [')

                first_batch = True

                while offset < total_count:
                    params = {
                        "where": "1=1",
                        "outFields": "*",
                        "returnGeometry": "true",
                        "outSR": "4326",
                        "resultOffset": str(offset),
                        "resultRecordCount": str(page_size),
                        "f": "geojson",
                    }

                    # Add spatial filter if provided
                    if geometry:
                        # TODO: Convert GeoJSON geometry to ArcGIS geometry format
                        pass

                    # Use _request with retry logic, but catch connection errors to reduce page size
                    logger.info(f"Fetching features {offset}-{offset+page_size} of {total_count}")

                    try:
                        geojson = await self._request(query_url, params=params)
                        features = geojson.get("features", [])
                        consecutive_connection_errors = 0  # Reset counter on success
                    except Exception as e:
                        error_msg = str(e)
                        # Check if this is a connection/protocol error
                        if "peer closed connection" in error_msg or "RemoteProtocolError" in error_msg:
                            consecutive_connection_errors += 1

                            # Reduce page size if we keep hitting connection errors
                            if page_size > 100 and consecutive_connection_errors >= 2:
                                old_page_size = page_size
                                page_size = max(100, page_size // 2)
                                logger.warning(
                                    f"Connection errors detected, reducing page size from {old_page_size} to {page_size}"
                                )
                                # Retry this offset with smaller page size
                                continue

                        # Re-raise if not a connection error or we can't reduce further
                        raise

                    if not features:
                        break

                    # Write features to file immediately (streaming)
                    for i, feature in enumerate(features):
                        # Add comma between features (but not before first)
                        if not first_batch or i > 0:
                            f.write(',')
                        else:
                            first_batch = False

                        json.dump(feature, f)
                        feature_count += 1

                    offset += len(features)

                    # Call progress callback after each batch
                    if progress_callback:
                        progress_callback(feature_count, total_count)

                    # Log progress every 10k features
                    if feature_count % 10000 == 0:
                        logger.info(f"Streamed {feature_count:,} / {total_count:,} features ({(feature_count/total_count)*100:.1f}%)")

                # Write GeoJSON footer
                f.write(']}')

            import os
            size_bytes = os.path.getsize(output_path)

            logger.info(f"Completed streaming download: {feature_count:,} features, {size_bytes:,} bytes")

            return DownloadResult(
                success=True,
                output_path=output_path,
                size_bytes=size_bytes,
                feature_count=feature_count,
            )

        except Exception as e:
            logger.error(f"Error in paged download: {e}")
            return DownloadResult(
                success=False,
                error=str(e),
            )

    async def get_preview(
        self,
        layer_url: str,
        limit: int = 100,
    ) -> Optional[dict]:
        """
        Get a preview sample of features from a layer.

        Args:
            layer_url: Full URL to the layer (e.g., .../FeatureServer/0)
            limit: Maximum number of features to return

        Returns:
            GeoJSON FeatureCollection or None if failed
        """
        try:
            query_url = f"{layer_url}/query"

            params = {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",  # WGS84
                "resultRecordCount": str(limit),
                "f": "geojson",
            }

            # Use _request with retry logic
            return await self._request(query_url, params=params)

        except Exception as e:
            logger.error(f"Error fetching preview from {layer_url}: {e}")
            return None

    async def get_feature_count(self, external_id: str) -> Optional[int]:
        """Get the number of features in a dataset."""
        try:
            layer_url = f"{self.base_url}/FeatureServer/{external_id}/query"

            params = {
                "where": "1=1",
                "returnCountOnly": "true",
                "f": "json",
            }

            result = await self._request(layer_url, params)
            return result.get("count")

        except Exception:
            return None

    async def get_oid_range(self, external_id: str) -> Optional[tuple[int, int]]:
        """
        Get OID range for parallel chunked downloads.

        This is ArcGIS-specific and very efficient.
        """
        try:
            layer_url = f"{self.base_url}/FeatureServer/{external_id}/query"

            # Get layer info to find OID field name
            layer_info = await self._request(f"{self.base_url}/FeatureServer/{external_id}")
            oid_field = "OBJECTID"  # Default

            for field in layer_info.get("fields", []):
                if field.get("type") == "esriFieldTypeOID":
                    oid_field = field.get("name")
                    break

            # Query for min/max OID using statistics
            params = {
                "outStatistics": f'[{{"statisticType":"min","onStatisticField":"{oid_field}","outStatisticFieldName":"MIN_OID"}},{{"statisticType":"max","onStatisticField":"{oid_field}","outStatisticFieldName":"MAX_OID"}}]',
                "f": "json",
            }

            result = await self._request(layer_url, params)

            if "features" in result and len(result["features"]) > 0:
                attrs = result["features"][0]["attributes"]
                return (attrs.get("MIN_OID"), attrs.get("MAX_OID"))

            return None

        except Exception:
            return None

    async def fetch_by_oid_range(
        self,
        layer_url: str,
        min_oid: int,
        max_oid: int,
        oid_field: str = "OBJECTID",
    ) -> Optional[list]:
        """
        Fetch features within OID range (for parallel downloads).

        This is the key to efficient large dataset downloads from ArcGIS.

        Args:
            layer_url: Full URL to the layer
            min_oid: Minimum OID value
            max_oid: Maximum OID value
            oid_field: Name of the OID field

        Returns:
            List of GeoJSON features or None if failed
        """
        try:
            query_url = f"{layer_url}/query"

            params = {
                "where": f"{oid_field} >= {min_oid} AND {oid_field} <= {max_oid}",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
            }

            # Use _request with retry logic
            geojson = await self._request(query_url, params=params)
            return geojson.get("features", [])

        except Exception as e:
            logger.error(f"Error fetching OID range {min_oid}-{max_oid}: {e}")
            return None

    async def download_parallel(
        self,
        layer_url: str,
        output_path: str,
        num_workers: int = 4,
        geometry: Optional[dict] = None,
    ) -> DownloadResult:
        """
        Download dataset using parallel OID-range queries.

        This is the most efficient method for large ArcGIS datasets.

        Args:
            layer_url: Full URL to the layer
            output_path: Path to save the GeoJSON file
            num_workers: Number of parallel download workers
            geometry: Optional spatial filter
        """
        try:
            # Get OID field name from layer info
            layer_info = await self._request(layer_url)
            oid_field = "OBJECTID"

            for field in layer_info.get("fields", []):
                if field.get("type") == "esriFieldTypeOID":
                    oid_field = field.get("name")
                    break

            # Get OID range
            oid_range = await self.get_oid_range_from_url(layer_url, oid_field)
            if not oid_range:
                # Fallback to paged download
                return await self.download_paged(layer_url, output_path)

            min_oid, max_oid = oid_range
            total_range = max_oid - min_oid + 1

            # Split into chunks
            chunk_size = max(1, total_range // num_workers)
            chunks = []

            for i in range(num_workers):
                chunk_min = min_oid + (i * chunk_size)
                chunk_max = min(min_oid + ((i + 1) * chunk_size) - 1, max_oid)

                if chunk_min <= max_oid:
                    chunks.append((chunk_min, chunk_max))

            logger.info(f"Downloading {total_range} OIDs in {len(chunks)} parallel chunks")

            # Download chunks in parallel
            import asyncio
            tasks = [
                self.fetch_by_oid_range(layer_url, chunk_min, chunk_max, oid_field)
                for chunk_min, chunk_max in chunks
            ]

            results = await asyncio.gather(*tasks)

            # Combine all features
            all_features = []
            for features in results:
                if features:
                    all_features.extend(features)

            # Write complete GeoJSON
            import json
            result_geojson = {
                "type": "FeatureCollection",
                "features": all_features
            }

            with open(output_path, "w") as f:
                json.dump(result_geojson, f)

            import os
            size_bytes = os.path.getsize(output_path)

            logger.info(f"Parallel download complete: {len(all_features)} features, {size_bytes} bytes")

            return DownloadResult(
                success=True,
                output_path=output_path,
                size_bytes=size_bytes,
                feature_count=len(all_features),
            )

        except Exception as e:
            logger.error(f"Error in parallel download: {e}")
            return DownloadResult(
                success=False,
                error=str(e),
            )

    async def get_oid_range_from_url(self, layer_url: str, oid_field: str = "OBJECTID") -> Optional[tuple[int, int]]:
        """
        Get OID range for a layer from its URL.

        Args:
            layer_url: Full URL to the layer
            oid_field: Name of the OID field

        Returns:
            Tuple of (min_oid, max_oid) or None
        """
        try:
            query_url = f"{layer_url}/query"

            # Query for min/max OID using statistics
            params = {
                "outStatistics": f'[{{"statisticType":"min","onStatisticField":"{oid_field}","outStatisticFieldName":"MIN_OID"}},{{"statisticType":"max","onStatisticField":"{oid_field}","outStatisticFieldName":"MAX_OID"}}]',
                "f": "json",
            }

            result = await self._request(query_url, params)

            if "features" in result and len(result["features"]) > 0:
                attrs = result["features"][0]["attributes"]
                return (attrs.get("MIN_OID"), attrs.get("MAX_OID"))

            return None

        except Exception:
            return None
