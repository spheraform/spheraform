"""Unit tests for ArcGIS adapter."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from spheraform_core.adapters.arcgis import ArcGISAdapter
from spheraform_core.adapters.base import (
    ServerCapabilities,
    DatasetMetadata,
    ChangeCheckResult,
)


@pytest.mark.unit
@pytest.mark.adapter
class TestArcGISAdapterInit:
    """Tests for ArcGIS adapter initialization."""

    def test_adapter_creation(self):
        """Test creating an adapter instance."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")
        assert adapter.base_url == "https://services.arcgis.com/test"
        assert adapter.provider_type == "arcgis"
        assert adapter.client is not None

    @pytest.mark.asyncio
    async def test_adapter_context_manager(self):
        """Test adapter as async context manager."""
        async with ArcGISAdapter(base_url="https://test.com") as adapter:
            assert adapter.client is not None
        # Client should be closed after exiting context


@pytest.mark.unit
@pytest.mark.adapter
class TestArcGISProbeCapabilities:
    """Tests for probing server capabilities."""

    @pytest.mark.asyncio
    async def test_probe_capabilities_with_services(
        self, mock_arcgis_server_info, mock_arcgis_service_info
    ):
        """Test probing capabilities from a server with services."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            # First call returns server info, second returns service info
            mock_request.side_effect = [
                mock_arcgis_server_info,
                mock_arcgis_service_info,
            ]

            capabilities = await adapter.probe_capabilities()

            assert isinstance(capabilities, ServerCapabilities)
            assert capabilities.max_features_per_request == 2000
            assert capabilities.supports_pagination is True
            assert capabilities.supports_result_offset is True
            assert capabilities.supports_oid_query is True
            assert "geojson" in capabilities.output_formats

    @pytest.mark.asyncio
    async def test_probe_capabilities_defaults_on_error(self):
        """Test that default capabilities are returned on error."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Exception("Network error")

            capabilities = await adapter.probe_capabilities()

            assert isinstance(capabilities, ServerCapabilities)
            # Should return defaults
            assert capabilities.max_features_per_request > 0


@pytest.mark.unit
@pytest.mark.adapter
class TestArcGISHealthCheck:
    """Tests for health check."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_arcgis_server_info):
        """Test successful health check."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_arcgis_server_info

            result = await adapter.health_check()

            assert result is True
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test failed health check."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Exception("Connection failed")

            result = await adapter.health_check()

            assert result is False


@pytest.mark.unit
@pytest.mark.adapter
class TestArcGISDiscoverDatasets:
    """Tests for discovering datasets."""

    @pytest.mark.asyncio
    async def test_discover_datasets(
        self,
        mock_arcgis_server_info,
        mock_arcgis_service_info,
        mock_arcgis_layer_info,
    ):
        """Test discovering datasets from a server."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            # Return server info, service info, and layer info
            mock_request.side_effect = [
                mock_arcgis_server_info,
                mock_arcgis_service_info,
                mock_arcgis_layer_info,
                mock_arcgis_layer_info,  # For second layer
            ]

            datasets = []
            async for dataset in adapter.discover_datasets():
                datasets.append(dataset)

            assert len(datasets) == 2  # Two layers in mock service
            assert all(isinstance(d, DatasetMetadata) for d in datasets)
            assert datasets[0].name == "Cities"
            assert datasets[0].external_id == "0"

    @pytest.mark.asyncio
    async def test_discover_datasets_with_folders(self):
        """Test discovering datasets from servers with folders."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        server_with_folders = {
            "folders": ["Folder1"],
            "services": [
                {"name": "Service1", "type": "FeatureServer"},
            ],
        }

        folder_catalog = {
            "services": [
                {"name": "Folder1/Service2", "type": "FeatureServer"},
            ],
        }

        service_info = {
            "layers": [
                {"id": 0, "name": "Layer1"},
            ],
        }

        layer_info = {
            "id": 0,
            "name": "Test Layer",
            "type": "Feature Layer",
            "extent": {"xmin": -180, "ymin": -90, "xmax": 180, "ymax": 90},
        }

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                server_with_folders,
                service_info,
                layer_info,
                folder_catalog,
                service_info,
                layer_info,
            ]

            datasets = []
            async for dataset in adapter.discover_datasets():
                datasets.append(dataset)

            assert len(datasets) == 2  # One from root, one from folder


@pytest.mark.unit
@pytest.mark.adapter
class TestArcGISMetadataExtraction:
    """Tests for metadata extraction."""

    def test_extract_metadata_with_extent(self, mock_arcgis_layer_info):
        """Test extracting metadata with spatial extent."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        metadata = adapter._extract_metadata(
            mock_arcgis_layer_info,
            "https://services.arcgis.com/test/FeatureServer/0",
        )

        assert metadata.name == "Cities"
        assert metadata.external_id == "0"
        assert metadata.bbox is not None
        assert metadata.bbox == (-180, -90, 180, 90)
        assert metadata.attribution == "Esri"

    def test_parse_edit_date(self, mock_arcgis_layer_info):
        """Test parsing edit date from layer info."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        edit_date = adapter._parse_edit_date(mock_arcgis_layer_info)

        assert isinstance(edit_date, datetime)
        # The mock has timestamp 1638360000000 (Dec 1, 2021)
        assert edit_date.year == 2021

    def test_parse_edit_date_missing(self):
        """Test parsing edit date when not available."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        layer_info = {"id": 0, "name": "Test"}
        edit_date = adapter._parse_edit_date(layer_info)

        assert edit_date is None


@pytest.mark.unit
@pytest.mark.adapter
class TestArcGISChangeDetection:
    """Tests for change detection."""

    @pytest.mark.asyncio
    async def test_check_changed_with_edit_date(self, mock_arcgis_layer_info):
        """Test change detection using edit date."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_arcgis_layer_info

            # Cached date is older than current
            cached_date = datetime(2021, 1, 1)

            result = await adapter.check_changed(
                dataset_id="abc-123",
                external_id="0",
                source_updated_at=cached_date,
            )

            assert result.changed is True
            assert result.result == ChangeCheckResult.CHANGED
            assert result.conclusive is True
            assert result.method == "arcgis_edit_date"

    @pytest.mark.asyncio
    async def test_check_unchanged_with_edit_date(self, mock_arcgis_layer_info):
        """Test detecting no change using edit date."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_arcgis_layer_info

            # Cached date is newer than current
            cached_date = datetime(2025, 1, 1)

            result = await adapter.check_changed(
                dataset_id="abc-123",
                external_id="0",
                source_updated_at=cached_date,
            )

            assert result.changed is False
            assert result.result == ChangeCheckResult.UNCHANGED
            assert result.conclusive is True

    @pytest.mark.asyncio
    async def test_check_changed_no_cached_date(self, mock_arcgis_layer_info):
        """Test change check with no cached date."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_arcgis_layer_info

            result = await adapter.check_changed(
                dataset_id="abc-123",
                external_id="0",
            )

            assert result.changed is True
            assert result.result == ChangeCheckResult.CHANGED

    @pytest.mark.asyncio
    async def test_check_changed_no_edit_date(self):
        """Test change check when layer has no edit date."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        layer_info = {"id": 0, "name": "Test"}

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = layer_info

            result = await adapter.check_changed(
                dataset_id="abc-123",
                external_id="0",
            )

            assert result.result == ChangeCheckResult.INCONCLUSIVE
            assert result.conclusive is False


@pytest.mark.unit
@pytest.mark.adapter
class TestArcGISFeatureCount:
    """Tests for getting feature counts."""

    @pytest.mark.asyncio
    async def test_get_feature_count(self, mock_arcgis_count_response):
        """Test getting feature count."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_arcgis_count_response

            count = await adapter.get_feature_count("0")

            assert count == 1000
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_feature_count_error(self):
        """Test feature count when request fails."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Exception("Request failed")

            count = await adapter.get_feature_count("0")

            assert count is None


@pytest.mark.unit
@pytest.mark.adapter
class TestArcGISOIDRange:
    """Tests for OID range queries."""

    @pytest.mark.asyncio
    async def test_get_oid_range(
        self, mock_arcgis_layer_info, mock_arcgis_oid_range_response
    ):
        """Test getting OID range."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                mock_arcgis_layer_info,
                mock_arcgis_oid_range_response,
            ]

            oid_range = await adapter.get_oid_range("0")

            assert oid_range is not None
            assert oid_range == (1, 1000)

    @pytest.mark.asyncio
    async def test_get_oid_range_error(self):
        """Test OID range when request fails."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Exception("Request failed")

            oid_range = await adapter.get_oid_range("0")

            assert oid_range is None


@pytest.mark.unit
@pytest.mark.adapter
class TestArcGISDownload:
    """Tests for download functionality."""

    @pytest.mark.asyncio
    async def test_download_simple(self, mock_arcgis_query_response, tmp_path):
        """Test simple download."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")
        output_path = str(tmp_path / "output.geojson")

        mock_response = MagicMock()
        mock_response.content = b'{"type":"FeatureCollection"}'
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            adapter.client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            result = await adapter.download_simple(
                external_id="0",
                output_path=output_path,
                format="geojson",
            )

            assert result.success is True
            assert result.output_path == output_path
            assert result.size_bytes > 0

    @pytest.mark.asyncio
    async def test_download_simple_error(self, tmp_path):
        """Test download with error."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")
        output_path = str(tmp_path / "output.geojson")

        with patch.object(
            adapter.client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = httpx.HTTPError("Download failed")

            result = await adapter.download_simple(
                external_id="0",
                output_path=output_path,
            )

            assert result.success is False
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_fetch_by_oid_range(self, mock_arcgis_layer_info, tmp_path):
        """Test fetching by OID range."""
        adapter = ArcGISAdapter(base_url="https://services.arcgis.com/test")
        output_path = str(tmp_path / "chunk.geojson")

        mock_response = MagicMock()
        mock_response.content = b'{"type":"FeatureCollection","features":[]}'
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_arcgis_layer_info

            with patch.object(
                adapter.client, "get", new_callable=AsyncMock
            ) as mock_get:
                mock_get.return_value = mock_response

                result = await adapter.fetch_by_oid_range(
                    external_id="0",
                    min_oid=1,
                    max_oid=100,
                    output_path=output_path,
                )

                assert result.success is True
                assert result.output_path == output_path
