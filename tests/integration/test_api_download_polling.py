"""Integration tests for download job polling and cancellation."""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from spheraform_core.models import Dataset, DownloadJob, JobStatus, DownloadStrategy


@pytest.mark.integration
class TestDownloadJobPolling:
    """Tests for download job polling endpoints."""

    def test_get_latest_download_job(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test getting the latest download job for a dataset."""
        # Create multiple jobs for same dataset
        old_job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.COMPLETED,
            strategy=DownloadStrategy.SIMPLE.value,
            chunks_completed=0,
            current_stage="complete",
            features_downloaded=1000,
            features_stored=1000,
        )
        db_session.add(old_job)
        db_session.flush()

        new_job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.RUNNING,
            strategy=DownloadStrategy.SIMPLE.value,
            chunks_completed=0,
            current_stage="storing",
            total_features=2000,
            features_downloaded=2000,
            features_stored=1500,
        )
        db_session.add(new_job)
        db_session.commit()

        response = client.get(f"/api/v1/download/datasets/{sample_dataset.id}/latest")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(new_job.id)
        assert data["status"] == "running"
        assert data["current_stage"] == "storing"
        assert data["features_stored"] == 1500

    def test_get_latest_download_job_not_found(
        self, client: TestClient, sample_dataset: Dataset
    ):
        """Test getting latest job when no jobs exist."""
        response = client.get(f"/api/v1/download/datasets/{sample_dataset.id}/latest")

        assert response.status_code == 404
        data = response.json()
        assert "No download jobs found" in data["detail"]

    def test_get_download_job_status_with_progress(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test getting job status with progress calculation."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.RUNNING,
            strategy=DownloadStrategy.SIMPLE.value,
            chunks_completed=0,
            current_stage="storing",
            total_features=10000,
            features_downloaded=10000,
            features_stored=7500,  # 75% of storing phase
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/api/v1/download/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["current_stage"] == "storing"
        # Progress should be 70% (download complete) + 75% of 25% (storing) = ~88.75%
        assert data["progress"] is not None
        assert 85 <= data["progress"] <= 95

    def test_get_download_job_status_indexing(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test getting job status during indexing."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.RUNNING,
            strategy=DownloadStrategy.SIMPLE.value,
            chunks_completed=0,
            current_stage="indexing",
            total_features=10000,
            features_downloaded=10000,
            features_stored=10000,
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/api/v1/download/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["current_stage"] == "indexing"
        assert data["progress"] == 95.0

    def test_get_download_job_status_completed(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test getting job status when completed."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.COMPLETED,
            strategy=DownloadStrategy.SIMPLE.value,
            chunks_completed=0,
            current_stage="complete",
            total_features=10000,
            features_downloaded=10000,
            features_stored=10000,
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/api/v1/download/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["progress"] == 100.0


@pytest.mark.integration
class TestDownloadJobCancellation:
    """Tests for download job cancellation."""

    def test_cancel_running_download_job(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test cancelling a running download job."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.RUNNING,
            strategy=DownloadStrategy.SIMPLE.value,
            chunks_completed=0,
            current_stage="storing",
            total_features=10000,
            features_downloaded=10000,
            features_stored=5000,
        )
        db_session.add(job)
        db_session.commit()

        response = client.post(f"/api/v1/download/jobs/{job.id}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["current_stage"] == "cancelled"

        # Verify job was actually cancelled in database
        db_session.refresh(job)
        assert job.status == JobStatus.CANCELLED
        assert job.completed_at is not None

    def test_cancel_pending_download_job(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test cancelling a pending download job."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.PENDING,
            strategy=DownloadStrategy.SIMPLE.value,
            chunks_completed=0,
            current_stage="pending",
        )
        db_session.add(job)
        db_session.commit()

        response = client.post(f"/api/v1/download/jobs/{job.id}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

        # Verify job was cancelled
        db_session.refresh(job)
        assert job.status == JobStatus.CANCELLED

    def test_cancel_completed_job_fails(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test that cancelling a completed job fails."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.COMPLETED,
            strategy=DownloadStrategy.SIMPLE.value,
            chunks_completed=0,
            current_stage="complete",
        )
        db_session.add(job)
        db_session.commit()

        response = client.post(f"/api/v1/download/jobs/{job.id}/cancel")

        assert response.status_code == 400
        data = response.json()
        assert "Cannot cancel" in data["detail"]

    def test_cancel_failed_job_fails(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test that cancelling a failed job fails."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.FAILED,
            strategy=DownloadStrategy.SIMPLE.value,
            chunks_completed=0,
            current_stage="failed",
            error="Network error",
        )
        db_session.add(job)
        db_session.commit()

        response = client.post(f"/api/v1/download/jobs/{job.id}/cancel")

        assert response.status_code == 400
        data = response.json()
        assert "Cannot cancel" in data["detail"]

    def test_cancel_cancelled_job_fails(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test that cancelling an already cancelled job fails."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.CANCELLED,
            strategy=DownloadStrategy.SIMPLE.value,
            chunks_completed=0,
            current_stage="cancelled",
        )
        db_session.add(job)
        db_session.commit()

        response = client.post(f"/api/v1/download/jobs/{job.id}/cancel")

        assert response.status_code == 400
        data = response.json()
        assert "Cannot cancel" in data["detail"]

    def test_cancel_nonexistent_job(self, client: TestClient):
        """Test cancelling a non-existent job."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.post(f"/api/v1/download/jobs/{fake_id}/cancel")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"]


@pytest.mark.integration
class TestDownloadJobProgressCalculation:
    """Tests for download job progress calculation logic."""

    def test_progress_during_downloading_phase(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test progress calculation during download phase."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.RUNNING,
            strategy=DownloadStrategy.SIMPLE.value,
            chunks_completed=0,
            current_stage="downloading",
            total_features=10000,
            features_downloaded=5000,  # 50% downloaded
            features_stored=0,
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/api/v1/download/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        # Download is 70% of total progress, so 50% of download = 35%
        assert data["progress"] == pytest.approx(35.0, rel=1e-2)

    def test_progress_during_storing_phase(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test progress calculation during storing phase."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.RUNNING,
            strategy=DownloadStrategy.SIMPLE.value,
            chunks_completed=0,
            current_stage="storing",
            total_features=10000,
            features_downloaded=10000,  # Download complete
            features_stored=5000,  # 50% stored
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/api/v1/download/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        # 70% (download) + 50% of 25% (storing) = 82.5%
        assert data["progress"] == pytest.approx(82.5, rel=1e-2)

    def test_progress_fallback_to_chunks(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test progress falls back to chunk-based when no feature counts."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.RUNNING,
            strategy=DownloadStrategy.CHUNKED.value,
            total_chunks=10,
            chunks_completed=6,
            current_stage="downloading",
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/api/v1/download/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        # 6/10 chunks = 60%
        assert data["progress"] == 60.0

    def test_progress_none_when_no_metrics(
        self, client: TestClient, db_session: Session, sample_dataset: Dataset
    ):
        """Test progress is None when no metrics available."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.PENDING,
            strategy=DownloadStrategy.SIMPLE.value,
            chunks_completed=0,
            current_stage="pending",
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/api/v1/download/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["progress"] is None
