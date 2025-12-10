"""Integration tests for crawl job polling and cancellation."""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from spheraform_core.models import Geoserver, CrawlJob, JobStatus


@pytest.mark.integration
class TestCrawlJobPolling:
    """Tests for crawl job polling endpoints."""

    def test_get_latest_crawl_job(
        self, client: TestClient, db_session: Session, sample_geoserver: Geoserver
    ):
        """Test getting the latest crawl job for a server."""
        # Create multiple jobs for same server
        old_job = CrawlJob(
            geoserver_id=sample_geoserver.id,
            status=JobStatus.COMPLETED,
            current_stage="complete",
            total_services=50,
            services_processed=50,
            datasets_discovered=200,
            datasets_new=150,
            datasets_updated=50,
        )
        db_session.add(old_job)
        db_session.flush()

        new_job = CrawlJob(
            geoserver_id=sample_geoserver.id,
            status=JobStatus.RUNNING,
            current_stage="processing_datasets",
            total_services=75,
            services_processed=40,
            datasets_discovered=150,
            datasets_new=100,
            datasets_updated=50,
        )
        db_session.add(new_job)
        db_session.commit()

        response = client.get(f"/api/v1/servers/{sample_geoserver.id}/crawl/latest")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(new_job.id)
        assert data["status"] == "running"
        assert data["current_stage"] == "processing_datasets"
        assert data["services_processed"] == 40
        assert data["datasets_discovered"] == 150

    def test_get_latest_crawl_job_not_found(
        self, client: TestClient, sample_geoserver: Geoserver
    ):
        """Test getting latest job when no jobs exist."""
        response = client.get(f"/api/v1/servers/{sample_geoserver.id}/crawl/latest")

        assert response.status_code == 404
        data = response.json()
        assert "No crawl jobs found" in data["detail"]

    def test_get_crawl_job_status(
        self, client: TestClient, db_session: Session, sample_geoserver: Geoserver
    ):
        """Test getting crawl job status."""
        job = CrawlJob(
            geoserver_id=sample_geoserver.id,
            status=JobStatus.RUNNING,
            current_stage="processing_datasets",
            total_services=100,
            services_processed=45,
            datasets_discovered=180,
            datasets_new=120,
            datasets_updated=60,
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/api/v1/servers/crawl/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["current_stage"] == "processing_datasets"
        assert data["total_services"] == 100
        assert data["services_processed"] == 45
        assert data["datasets_discovered"] == 180
        assert data["datasets_new"] == 120
        assert data["datasets_updated"] == 60

    def test_get_crawl_job_status_not_found(self, client: TestClient):
        """Test getting status of non-existent crawl job."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.get(f"/api/v1/servers/crawl/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"]


@pytest.mark.integration
class TestCrawlJobCancellation:
    """Tests for crawl job cancellation."""

    def test_cancel_running_crawl_job(
        self, client: TestClient, db_session: Session, sample_geoserver: Geoserver
    ):
        """Test cancelling a running crawl job."""
        job = CrawlJob(
            geoserver_id=sample_geoserver.id,
            status=JobStatus.RUNNING,
            current_stage="processing_datasets",
            total_services=100,
            services_processed=45,
            datasets_discovered=180,
            datasets_new=120,
            datasets_updated=60,
        )
        db_session.add(job)
        db_session.commit()

        response = client.post(f"/api/v1/servers/crawl/{job.id}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["current_stage"] == "cancelled"

        # Verify job was actually cancelled in database
        db_session.refresh(job)
        assert job.status == JobStatus.CANCELLED
        assert job.completed_at is not None

    def test_cancel_pending_crawl_job(
        self, client: TestClient, db_session: Session, sample_geoserver: Geoserver
    ):
        """Test cancelling a pending crawl job."""
        job = CrawlJob(
            geoserver_id=sample_geoserver.id,
            status=JobStatus.PENDING,
            current_stage="pending",
            total_services=0,
            services_processed=0,
            datasets_discovered=0,
            datasets_new=0,
            datasets_updated=0,
        )
        db_session.add(job)
        db_session.commit()

        response = client.post(f"/api/v1/servers/crawl/{job.id}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

        # Verify job was cancelled
        db_session.refresh(job)
        assert job.status == JobStatus.CANCELLED

    def test_cancel_completed_crawl_job_fails(
        self, client: TestClient, db_session: Session, sample_geoserver: Geoserver
    ):
        """Test that cancelling a completed crawl job fails."""
        job = CrawlJob(
            geoserver_id=sample_geoserver.id,
            status=JobStatus.COMPLETED,
            current_stage="complete",
            total_services=100,
            services_processed=100,
            datasets_discovered=400,
            datasets_new=250,
            datasets_updated=150,
        )
        db_session.add(job)
        db_session.commit()

        response = client.post(f"/api/v1/servers/crawl/{job.id}/cancel")

        assert response.status_code == 400
        data = response.json()
        assert "Cannot cancel" in data["detail"]

    def test_cancel_failed_crawl_job_fails(
        self, client: TestClient, db_session: Session, sample_geoserver: Geoserver
    ):
        """Test that cancelling a failed crawl job fails."""
        job = CrawlJob(
            geoserver_id=sample_geoserver.id,
            status=JobStatus.FAILED,
            current_stage="failed",
            error="Server unreachable",
            total_services=0,
            services_processed=0,
            datasets_discovered=0,
            datasets_new=0,
            datasets_updated=0,
        )
        db_session.add(job)
        db_session.commit()

        response = client.post(f"/api/v1/servers/crawl/{job.id}/cancel")

        assert response.status_code == 400
        data = response.json()
        assert "Cannot cancel" in data["detail"]

    def test_cancel_cancelled_crawl_job_fails(
        self, client: TestClient, db_session: Session, sample_geoserver: Geoserver
    ):
        """Test that cancelling an already cancelled crawl job fails."""
        job = CrawlJob(
            geoserver_id=sample_geoserver.id,
            status=JobStatus.CANCELLED,
            current_stage="cancelled",
            total_services=100,
            services_processed=45,
            datasets_discovered=180,
            datasets_new=120,
            datasets_updated=60,
        )
        db_session.add(job)
        db_session.commit()

        response = client.post(f"/api/v1/servers/crawl/{job.id}/cancel")

        assert response.status_code == 400
        data = response.json()
        assert "Cannot cancel" in data["detail"]

    def test_cancel_nonexistent_crawl_job(self, client: TestClient):
        """Test cancelling a non-existent crawl job."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.post(f"/api/v1/servers/crawl/{fake_id}/cancel")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"]


@pytest.mark.integration
class TestCrawlJobStages:
    """Tests for different crawl job stages."""

    def test_crawl_job_counting_services_stage(
        self, client: TestClient, db_session: Session, sample_geoserver: Geoserver
    ):
        """Test crawl job in counting_services stage."""
        job = CrawlJob(
            geoserver_id=sample_geoserver.id,
            status=JobStatus.RUNNING,
            current_stage="counting_services",
            total_services=None,  # Not yet counted
            services_processed=0,
            datasets_discovered=0,
            datasets_new=0,
            datasets_updated=0,
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/api/v1/servers/crawl/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["current_stage"] == "counting_services"
        assert data["total_services"] is None

    def test_crawl_job_processing_datasets_stage(
        self, client: TestClient, db_session: Session, sample_geoserver: Geoserver
    ):
        """Test crawl job in processing_datasets stage."""
        job = CrawlJob(
            geoserver_id=sample_geoserver.id,
            status=JobStatus.RUNNING,
            current_stage="processing_datasets",
            total_services=150,
            services_processed=75,
            datasets_discovered=300,
            datasets_new=200,
            datasets_updated=100,
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/api/v1/servers/crawl/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["current_stage"] == "processing_datasets"
        assert data["services_processed"] == 75
        assert data["datasets_discovered"] == 300

    def test_crawl_job_finalizing_stage(
        self, client: TestClient, db_session: Session, sample_geoserver: Geoserver
    ):
        """Test crawl job in finalizing stage."""
        job = CrawlJob(
            geoserver_id=sample_geoserver.id,
            status=JobStatus.RUNNING,
            current_stage="finalizing",
            total_services=150,
            services_processed=150,
            datasets_discovered=600,
            datasets_new=400,
            datasets_updated=200,
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/api/v1/servers/crawl/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["current_stage"] == "finalizing"
        assert data["services_processed"] == data["total_services"]

    def test_crawl_job_complete_stage(
        self, client: TestClient, db_session: Session, sample_geoserver: Geoserver
    ):
        """Test crawl job in complete stage."""
        job = CrawlJob(
            geoserver_id=sample_geoserver.id,
            status=JobStatus.COMPLETED,
            current_stage="complete",
            total_services=150,
            services_processed=150,
            datasets_discovered=600,
            datasets_new=400,
            datasets_updated=200,
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/api/v1/servers/crawl/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["current_stage"] == "complete"
