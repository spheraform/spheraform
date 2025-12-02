"""Integration tests for download API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch, AsyncMock, MagicMock

from spheraform_core.models import Dataset, DownloadJob, JobStatus


@pytest.mark.integration
class TestDownloadAPI:
    """Tests for /download endpoint."""

    @pytest.mark.asyncio
    async def test_download_small_dataset(
        self, client: TestClient, sample_dataset: Dataset, db_session: Session
    ):
        """Test downloading a small dataset directly."""
        from spheraform_core.adapters.base import DownloadResult

        # Mock adapter to return small dataset
        mock_result = DownloadResult(
            success=True,
            output_path="/tmp/test.geojson",
            size_bytes=1024,
        )

        with patch(
            "spheraform_api.routers.download.ArcGISAdapter"
        ) as mock_adapter_class:
            mock_adapter = AsyncMock()
            mock_adapter.download_simple.return_value = mock_result
            mock_adapter.__aenter__.return_value = mock_adapter
            mock_adapter.__aexit__.return_value = None
            mock_adapter_class.return_value = mock_adapter

            download_request = {
                "dataset_ids": [str(sample_dataset.id)],
                "format": "geojson",
            }

            response = client.post("/download/", json=download_request)

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"
            assert "download_url" in data

    @pytest.mark.asyncio
    async def test_download_large_dataset_creates_job(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test that downloading a large dataset creates a background job."""
        # Create large dataset
        large_dataset = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="Large Dataset",
            access_url="https://test.com/0",
            feature_count=1000000,  # Large dataset
        )
        db_session.add(large_dataset)
        db_session.commit()

        download_request = {
            "dataset_ids": [str(large_dataset.id)],
            "format": "geojson",
        }

        response = client.post("/download/", json=download_request)

        assert response.status_code == 202  # Accepted
        data = response.json()
        assert data["status"] == "pending"
        assert "job_id" in data

        # Verify job was created in database
        job = db_session.query(DownloadJob).filter_by(dataset_id=large_dataset.id).first()
        assert job is not None
        assert job.status == JobStatus.PENDING

    def test_download_multiple_datasets(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test downloading multiple datasets."""
        dataset1 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="Dataset 1",
            access_url="https://test.com/0",
            feature_count=100,
        )
        dataset2 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="1",
            name="Dataset 2",
            access_url="https://test.com/1",
            feature_count=200,
        )
        db_session.add_all([dataset1, dataset2])
        db_session.commit()

        download_request = {
            "dataset_ids": [str(dataset1.id), str(dataset2.id)],
            "format": "geojson",
        }

        response = client.post("/download/", json=download_request)

        # Should create a job for multiple datasets
        assert response.status_code in [200, 202]

    def test_download_with_bbox_filter(
        self, client: TestClient, sample_dataset: Dataset
    ):
        """Test downloading with bounding box filter."""
        download_request = {
            "dataset_ids": [str(sample_dataset.id)],
            "format": "geojson",
            "bbox": [-122.5, 37.7, -122.3, 37.9],
        }

        response = client.post("/download/", json=download_request)

        assert response.status_code in [200, 202]

    def test_download_with_geometry_filter(
        self, client: TestClient, sample_dataset: Dataset
    ):
        """Test downloading with geometry filter."""
        download_request = {
            "dataset_ids": [str(sample_dataset.id)],
            "format": "geojson",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-122.5, 37.7],
                        [-122.5, 37.9],
                        [-122.3, 37.9],
                        [-122.3, 37.7],
                        [-122.5, 37.7],
                    ]
                ],
            },
        }

        response = client.post("/download/", json=download_request)

        assert response.status_code in [200, 202]

    def test_download_invalid_format(
        self, client: TestClient, sample_dataset: Dataset
    ):
        """Test downloading with invalid format."""
        download_request = {
            "dataset_ids": [str(sample_dataset.id)],
            "format": "invalid_format",
        }

        response = client.post("/download/", json=download_request)

        assert response.status_code == 422  # Validation error

    def test_download_nonexistent_dataset(self, client: TestClient):
        """Test downloading a non-existent dataset."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        download_request = {
            "dataset_ids": [fake_id],
            "format": "geojson",
        }

        response = client.post("/download/", json=download_request)

        assert response.status_code == 404


@pytest.mark.integration
class TestDownloadJobStatus:
    """Tests for checking download job status."""

    def test_get_job_status_pending(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test getting status of pending job."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.PENDING,
            format="geojson",
            total_chunks=10,
            completed_chunks=0,
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/download/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["total_chunks"] == 10
        assert data["completed_chunks"] == 0

    def test_get_job_status_in_progress(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test getting status of in-progress job."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.IN_PROGRESS,
            format="geojson",
            total_chunks=10,
            completed_chunks=3,
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/download/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"
        assert data["completed_chunks"] == 3

    def test_get_job_status_completed(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test getting status of completed job."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.COMPLETED,
            format="geojson",
            output_path="/tmp/result.geojson",
            total_chunks=10,
            completed_chunks=10,
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/download/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["completed_chunks"] == 10
        assert "output_path" in data

    def test_get_job_status_failed(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test getting status of failed job."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.FAILED,
            format="geojson",
            error_message="Download failed: Network error",
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/download/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "error_message" in data

    def test_get_job_status_not_found(self, client: TestClient):
        """Test getting status of non-existent job."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.get(f"/download/jobs/{fake_id}")

        assert response.status_code == 404


@pytest.mark.integration
class TestDownloadJobResult:
    """Tests for downloading job results."""

    def test_download_job_result_completed(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset, tmp_path
    ):
        """Test downloading result of completed job."""
        # Create a test file
        output_file = tmp_path / "result.geojson"
        output_file.write_text('{"type":"FeatureCollection","features":[]}')

        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.COMPLETED,
            format="geojson",
            output_path=str(output_file),
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/download/jobs/{job.id}/download")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/geo+json"

    def test_download_job_result_not_completed(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test downloading result when job is not completed."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.IN_PROGRESS,
            format="geojson",
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/download/jobs/{job.id}/download")

        assert response.status_code == 400  # Bad request - job not ready

    def test_download_job_result_not_found(self, client: TestClient):
        """Test downloading result of non-existent job."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.get(f"/download/jobs/{fake_id}/download")

        assert response.status_code == 404


@pytest.mark.integration
class TestDownloadFormats:
    """Tests for different download formats."""

    def test_download_geojson_format(
        self, client: TestClient, sample_dataset: Dataset
    ):
        """Test downloading in GeoJSON format."""
        download_request = {
            "dataset_ids": [str(sample_dataset.id)],
            "format": "geojson",
        }

        response = client.post("/download/", json=download_request)

        assert response.status_code in [200, 202]

    def test_download_shapefile_format(
        self, client: TestClient, sample_dataset: Dataset
    ):
        """Test downloading in Shapefile format."""
        download_request = {
            "dataset_ids": [str(sample_dataset.id)],
            "format": "shapefile",
        }

        response = client.post("/download/", json=download_request)

        assert response.status_code in [200, 202]

    def test_download_geopackage_format(
        self, client: TestClient, sample_dataset: Dataset
    ):
        """Test downloading in GeoPackage format."""
        download_request = {
            "dataset_ids": [str(sample_dataset.id)],
            "format": "gpkg",
        }

        response = client.post("/download/", json=download_request)

        assert response.status_code in [200, 202]
