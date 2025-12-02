"""Integration tests for server management API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import AsyncMock, patch

from spheraform_core.models import Geoserver, ProviderType, HealthStatus


@pytest.mark.integration
class TestServersAPI:
    """Tests for /servers endpoints."""

    def test_create_server(self, client: TestClient, db_session: Session):
        """Test creating a new server."""
        server_data = {
            "name": "Test ArcGIS Server",
            "base_url": "https://services.arcgis.com/test",
            "provider_type": "arcgis",
            "probe_frequency_hours": 24,
        }

        response = client.post("/servers/", json=server_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test ArcGIS Server"
        assert data["provider_type"] == "arcgis"
        assert data["health_status"] == "unknown"
        assert "id" in data

        # Verify in database
        server = db_session.query(Geoserver).filter_by(name="Test ArcGIS Server").first()
        assert server is not None
        assert server.base_url == "https://services.arcgis.com/test"

    def test_create_server_with_auth(self, client: TestClient, db_session: Session):
        """Test creating a server with authentication."""
        server_data = {
            "name": "Secured Server",
            "base_url": "https://secure.arcgis.com/test",
            "provider_type": "arcgis",
            "auth_config": {
                "type": "api_key",
                "key": "secret123",
            },
        }

        response = client.post("/servers/", json=server_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Secured Server"
        assert "auth_config" in data

    def test_create_server_invalid_provider(self, client: TestClient):
        """Test creating server with invalid provider type."""
        server_data = {
            "name": "Invalid Server",
            "base_url": "https://test.com",
            "provider_type": "invalid_provider",
        }

        response = client.post("/servers/", json=server_data)

        assert response.status_code == 422  # Validation error

    def test_list_servers_empty(self, client: TestClient):
        """Test listing servers when none exist."""
        response = client.get("/servers/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_servers(self, client: TestClient, sample_geoserver: Geoserver):
        """Test listing servers."""
        response = client.get("/servers/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == sample_geoserver.name
        assert data[0]["provider_type"] == "arcgis"

    def test_list_servers_filter_by_provider(
        self, client: TestClient, db_session: Session
    ):
        """Test filtering servers by provider type."""
        # Create servers with different provider types
        arcgis_server = Geoserver(
            name="ArcGIS Server",
            base_url="https://arcgis.com",
            provider_type=ProviderType.ARCGIS,
        )
        wfs_server = Geoserver(
            name="WFS Server",
            base_url="https://wfs.com",
            provider_type=ProviderType.WFS,
        )
        db_session.add_all([arcgis_server, wfs_server])
        db_session.commit()

        response = client.get("/servers/?provider_type=arcgis")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["provider_type"] == "arcgis"

    def test_get_server(self, client: TestClient, sample_geoserver: Geoserver):
        """Test getting a specific server."""
        response = client.get(f"/servers/{sample_geoserver.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_geoserver.id)
        assert data["name"] == sample_geoserver.name

    def test_get_server_not_found(self, client: TestClient):
        """Test getting a non-existent server."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/servers/{fake_id}")

        assert response.status_code == 404

    def test_update_server(self, client: TestClient, sample_geoserver: Geoserver):
        """Test updating a server."""
        update_data = {
            "name": "Updated Server Name",
            "probe_frequency_hours": 48,
        }

        response = client.put(f"/servers/{sample_geoserver.id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Server Name"
        assert data["probe_frequency_hours"] == 48

    def test_update_server_not_found(self, client: TestClient):
        """Test updating a non-existent server."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        update_data = {"name": "Updated"}

        response = client.put(f"/servers/{fake_id}", json=update_data)

        assert response.status_code == 404

    def test_delete_server(
        self, client: TestClient, sample_geoserver: Geoserver, db_session: Session
    ):
        """Test deleting a server."""
        server_id = sample_geoserver.id

        response = client.delete(f"/servers/{server_id}")

        assert response.status_code == 204

        # Verify deleted from database
        server = db_session.query(Geoserver).filter_by(id=server_id).first()
        assert server is None

    def test_delete_server_not_found(self, client: TestClient):
        """Test deleting a non-existent server."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.delete(f"/servers/{fake_id}")

        assert response.status_code == 404


@pytest.mark.integration
class TestServerHealthCheck:
    """Tests for server health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_success(
        self, client: TestClient, sample_geoserver: Geoserver
    ):
        """Test health check that succeeds."""
        with patch(
            "spheraform_api.routers.servers.ArcGISAdapter"
        ) as mock_adapter_class:
            mock_adapter = AsyncMock()
            mock_adapter.health_check.return_value = True
            mock_adapter.__aenter__.return_value = mock_adapter
            mock_adapter.__aexit__.return_value = None
            mock_adapter_class.return_value = mock_adapter

            response = client.get(f"/servers/{sample_geoserver.id}/health")

            assert response.status_code == 200
            data = response.json()
            assert data["healthy"] is True

    @pytest.mark.asyncio
    async def test_health_check_failure(
        self, client: TestClient, sample_geoserver: Geoserver
    ):
        """Test health check that fails."""
        with patch(
            "spheraform_api.routers.servers.ArcGISAdapter"
        ) as mock_adapter_class:
            mock_adapter = AsyncMock()
            mock_adapter.health_check.return_value = False
            mock_adapter.__aenter__.return_value = mock_adapter
            mock_adapter.__aexit__.return_value = None
            mock_adapter_class.return_value = mock_adapter

            response = client.get(f"/servers/{sample_geoserver.id}/health")

            assert response.status_code == 200
            data = response.json()
            assert data["healthy"] is False


@pytest.mark.integration
class TestServerCrawl:
    """Tests for crawling servers to discover datasets."""

    @pytest.mark.asyncio
    async def test_crawl_server(
        self, client: TestClient, sample_geoserver: Geoserver, db_session: Session
    ):
        """Test crawling a server to discover datasets."""
        from spheraform_core.adapters.base import DatasetMetadata

        # Mock datasets to be discovered
        mock_datasets = [
            DatasetMetadata(
                external_id="0",
                name="Test Dataset 1",
                access_url="https://test.com/FeatureServer/0",
                description="Test dataset 1",
                keywords=["test"],
                bbox=(-180, -90, 180, 90),
                feature_count=1000,
            ),
            DatasetMetadata(
                external_id="1",
                name="Test Dataset 2",
                access_url="https://test.com/FeatureServer/1",
                description="Test dataset 2",
                keywords=["test"],
                bbox=(-180, -90, 180, 90),
                feature_count=500,
            ),
        ]

        async def mock_discover():
            for dataset in mock_datasets:
                yield dataset

        with patch(
            "spheraform_api.routers.servers.ArcGISAdapter"
        ) as mock_adapter_class:
            mock_adapter = AsyncMock()
            mock_adapter.discover_datasets = mock_discover
            mock_adapter.__aenter__.return_value = mock_adapter
            mock_adapter.__aexit__.return_value = None
            mock_adapter_class.return_value = mock_adapter

            response = client.post(f"/servers/{sample_geoserver.id}/crawl")

            assert response.status_code == 200
            data = response.json()
            assert data["datasets_discovered"] == 2
            assert data["datasets_updated"] == 2
            assert data["datasets_new"] == 2

            # Verify datasets in database
            from spheraform_core.models import Dataset

            datasets = (
                db_session.query(Dataset)
                .filter_by(geoserver_id=sample_geoserver.id)
                .all()
            )
            assert len(datasets) == 2

    @pytest.mark.asyncio
    async def test_crawl_server_not_found(self, client: TestClient):
        """Test crawling a non-existent server."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.post(f"/servers/{fake_id}/crawl")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_crawl_server_updates_existing_datasets(
        self, client: TestClient, sample_dataset, db_session: Session
    ):
        """Test that crawling updates existing datasets."""
        from spheraform_core.adapters.base import DatasetMetadata

        # Mock updated dataset
        updated_metadata = DatasetMetadata(
            external_id=sample_dataset.external_id,
            name="Updated Dataset Name",
            access_url=sample_dataset.access_url,
            description="Updated description",
            keywords=["updated"],
            feature_count=2000,  # Changed
        )

        async def mock_discover():
            yield updated_metadata

        with patch(
            "spheraform_api.routers.servers.ArcGISAdapter"
        ) as mock_adapter_class:
            mock_adapter = AsyncMock()
            mock_adapter.discover_datasets = mock_discover
            mock_adapter.__aenter__.return_value = mock_adapter
            mock_adapter.__aexit__.return_value = None
            mock_adapter_class.return_value = mock_adapter

            response = client.post(f"/servers/{sample_dataset.geoserver_id}/crawl")

            assert response.status_code == 200
            data = response.json()
            assert data["datasets_updated"] == 1
            assert data["datasets_new"] == 0

            # Verify dataset was updated
            db_session.refresh(sample_dataset)
            assert sample_dataset.name == "Updated Dataset Name"
            assert sample_dataset.feature_count == 2000
