"""Integration tests for datasets API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from spheraform_core.models import Dataset, DownloadStrategy


@pytest.mark.integration
class TestDatasetsAPI:
    """Tests for /datasets endpoints."""

    def test_list_datasets_empty(self, client: TestClient):
        """Test listing datasets when none exist."""
        response = client.get("/datasets/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_datasets(self, client: TestClient, sample_dataset: Dataset):
        """Test listing datasets."""
        response = client.get("/datasets/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == sample_dataset.name
        assert data[0]["external_id"] == sample_dataset.external_id

    def test_list_datasets_pagination(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test dataset pagination."""
        # Create multiple datasets
        for i in range(15):
            dataset = Dataset(
                geoserver_id=sample_geoserver.id,
                external_id=str(i),
                name=f"Dataset {i}",
                access_url=f"https://test.com/FeatureServer/{i}",
                download_strategy=DownloadStrategy.SIMPLE,
            )
            db_session.add(dataset)
        db_session.commit()

        # Get first page
        response = client.get("/datasets/?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 10

        # Get second page
        response = client.get("/datasets/?skip=10&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    def test_list_datasets_filter_by_server(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test filtering datasets by server."""
        from spheraform_core.models import Geoserver, ProviderType

        # Create another server
        other_server = Geoserver(
            name="Other Server",
            base_url="https://other.com",
            provider_type=ProviderType.ARCGIS,
        )
        db_session.add(other_server)
        db_session.commit()

        # Create datasets for both servers
        dataset1 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="Dataset 1",
            access_url="https://test.com/0",
        )
        dataset2 = Dataset(
            geoserver_id=other_server.id,
            external_id="0",
            name="Dataset 2",
            access_url="https://other.com/0",
        )
        db_session.add_all([dataset1, dataset2])
        db_session.commit()

        # Filter by first server
        response = client.get(f"/datasets/?geoserver_id={sample_geoserver.id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Dataset 1"

    def test_list_datasets_filter_active(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test filtering datasets by active status."""
        # Create active and inactive datasets
        active = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="Active Dataset",
            access_url="https://test.com/0",
            is_active=True,
        )
        inactive = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="1",
            name="Inactive Dataset",
            access_url="https://test.com/1",
            is_active=False,
        )
        db_session.add_all([active, inactive])
        db_session.commit()

        # Filter active only
        response = client.get("/datasets/?is_active=true")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Active Dataset"

    def test_get_dataset(self, client: TestClient, sample_dataset: Dataset):
        """Test getting a specific dataset."""
        response = client.get(f"/datasets/{sample_dataset.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_dataset.id)
        assert data["name"] == sample_dataset.name
        assert data["description"] == sample_dataset.description
        assert "keywords" in data
        assert "themes" in data

    def test_get_dataset_not_found(self, client: TestClient):
        """Test getting a non-existent dataset."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/datasets/{fake_id}")

        assert response.status_code == 404

    def test_get_dataset_includes_geoserver(
        self, client: TestClient, sample_dataset: Dataset
    ):
        """Test that dataset response includes geoserver info."""
        response = client.get(f"/datasets/{sample_dataset.id}")

        assert response.status_code == 200
        data = response.json()
        assert "geoserver_id" in data
        assert data["geoserver_id"] == str(sample_dataset.geoserver_id)


@pytest.mark.integration
class TestDatasetPreview:
    """Tests for dataset preview endpoint."""

    @pytest.mark.asyncio
    async def test_preview_dataset(self, client: TestClient, sample_dataset: Dataset):
        """Test previewing dataset features."""
        from unittest.mock import patch, AsyncMock, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": 1,
                    "geometry": {"type": "Point", "coordinates": [-122.4, 37.8]},
                    "properties": {"name": "Test Feature"},
                }
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch(
            "spheraform_api.routers.datasets.ArcGISAdapter"
        ) as mock_adapter_class:
            mock_adapter = AsyncMock()
            mock_adapter.client.get.return_value = mock_response
            mock_adapter.__aenter__.return_value = mock_adapter
            mock_adapter.__aexit__.return_value = None
            mock_adapter_class.return_value = mock_adapter

            response = client.get(f"/datasets/{sample_dataset.id}/preview")

            assert response.status_code == 200
            data = response.json()
            assert data["type"] == "FeatureCollection"
            assert len(data["features"]) == 1

    @pytest.mark.asyncio
    async def test_preview_dataset_not_found(self, client: TestClient):
        """Test previewing a non-existent dataset."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/datasets/{fake_id}/preview")

        assert response.status_code == 404


@pytest.mark.integration
class TestDatasetRefresh:
    """Tests for refreshing dataset metadata."""

    @pytest.mark.asyncio
    async def test_refresh_dataset(
        self, client: TestClient, sample_dataset: Dataset, db_session: Session
    ):
        """Test refreshing a dataset's metadata."""
        from unittest.mock import patch, AsyncMock
        from spheraform_core.adapters.base import DatasetMetadata

        updated_metadata = DatasetMetadata(
            external_id=sample_dataset.external_id,
            name="Updated Name",
            access_url=sample_dataset.access_url,
            description="Updated description",
            feature_count=5000,
        )

        async def mock_discover():
            yield updated_metadata

        with patch(
            "spheraform_api.routers.datasets.ArcGISAdapter"
        ) as mock_adapter_class:
            mock_adapter = AsyncMock()
            mock_adapter.discover_datasets = mock_discover
            mock_adapter.__aenter__.return_value = mock_adapter
            mock_adapter.__aexit__.return_value = None
            mock_adapter_class.return_value = mock_adapter

            response = client.post(f"/datasets/{sample_dataset.id}/refresh")

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Updated Name"
            assert data["feature_count"] == 5000

    @pytest.mark.asyncio
    async def test_refresh_dataset_not_found(self, client: TestClient):
        """Test refreshing a non-existent dataset."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.post(f"/datasets/{fake_id}/refresh")

        assert response.status_code == 404
