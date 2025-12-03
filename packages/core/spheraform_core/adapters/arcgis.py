"""ArcGIS REST API adapter."""

import asyncio
from datetime import datetime
from typing import AsyncIterator, Optional, Dict
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
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
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
            print(f"ArcGIS adapter using proxy: {proxy_url} for {base_url}")
        else:
            print(f"ArcGIS adapter NOT using proxy for {base_url}")

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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _request(self, url: str, params: dict = None) -> dict:
        """Make HTTP request with retry logic."""
        headers = self._build_auth_headers()
        params = params or {}
        params.setdefault("f", "pjson")  # Use pjson for better compatibility with ArcGIS REST

        try:
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            # Log response details for debugging
            if hasattr(e, 'response') and e.response is not None:
                print(f"Request failed for {url}: {e}")
                print(f"Response status: {e.response.status_code}")
                print(f"Response body (first 500 chars): {e.response.text[:500]}")
            else:
                print(f"Request failed for {url}: {e}")
            raise

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
            print(f"Error discovering datasets: {e}")

    async def _process_service(self, service: dict) -> AsyncIterator[DatasetMetadata]:
        """Process a single ArcGIS service and yield its layers."""
        service_name = service.get("name")
        service_type = service.get("type")

        # Only process FeatureServers (MapServers can also work but focus on Feature first)
        if service_type not in ["FeatureServer", "MapServer"]:
            return

        service_url = f"{self.base_url}/{service_name}/{service_type}"

        try:
            service_info = await self._request(service_url)

            # Process each layer in the service
            for layer in service_info.get("layers", []):
                layer_id = layer.get("id")
                layer_name = layer.get("name")

                # Get detailed layer information
                layer_url = f"{service_url}/{layer_id}"
                layer_info = await self._request(layer_url)

                # Extract metadata
                metadata = self._extract_metadata(layer_info, layer_url)
                yield metadata

        except Exception as e:
            print(f"Error processing service {service_name}: {e}")

    def _extract_metadata(self, layer_info: dict, layer_url: str) -> DatasetMetadata:
        """Extract metadata from ArcGIS layer info."""
        # Parse extent to bbox
        bbox = None
        if "extent" in layer_info:
            extent = layer_info["extent"]
            bbox = (
                extent.get("xmin"),
                extent.get("ymin"),
                extent.get("xmax"),
                extent.get("ymax"),
            )

        # Get feature count if available
        feature_count = None
        # Note: ArcGIS doesn't always provide count in layer info
        # We'd need to query with returnCountOnly=true

        # Extract keywords from description/tags
        keywords = []
        if "description" in layer_info:
            # Simple keyword extraction - can be improved
            keywords = layer_info["description"].split()[:10]

        return DatasetMetadata(
            external_id=str(layer_info.get("id")),
            name=layer_info.get("name", "Unnamed Layer"),
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

            response = await self.client.get(layer_url, params=params)
            response.raise_for_status()

            # Write to file
            with open(output_path, "wb") as f:
                f.write(response.content)

            return DownloadResult(
                success=True,
                output_path=output_path,
                size_bytes=len(response.content),
            )

        except Exception as e:
            return DownloadResult(
                success=False,
                error=str(e),
            )

    async def download_paged(
        self,
        external_id: str,
        output_path: str,
        geometry: Optional[dict] = None,
        format: str = "geojson",
    ) -> DownloadResult:
        """
        Download dataset using offset-based pagination.

        For datasets larger than max_features_per_request.
        """
        # TODO: Implement paged download
        pass

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

        except Exception as e:
            print(f"Error getting OID range: {e}")
            return None

    async def fetch_by_oid_range(
        self,
        external_id: str,
        min_oid: int,
        max_oid: int,
        output_path: str,
    ) -> DownloadResult:
        """
        Fetch features within OID range (for parallel downloads).

        This is the key to efficient large dataset downloads from ArcGIS.
        """
        try:
            layer_url = f"{self.base_url}/FeatureServer/{external_id}/query"

            # Get OID field name
            layer_info = await self._request(f"{self.base_url}/FeatureServer/{external_id}")
            oid_field = "OBJECTID"

            for field in layer_info.get("fields", []):
                if field.get("type") == "esriFieldTypeOID":
                    oid_field = field.get("name")
                    break

            params = {
                "where": f"{oid_field} >= {min_oid} AND {oid_field} <= {max_oid}",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
            }

            response = await self.client.get(layer_url, params=params)
            response.raise_for_status()

            # Write to file
            with open(output_path, "wb") as f:
                f.write(response.content)

            return DownloadResult(
                success=True,
                output_path=output_path,
                size_bytes=len(response.content),
            )

        except Exception as e:
            return DownloadResult(
                success=False,
                error=str(e),
            )
