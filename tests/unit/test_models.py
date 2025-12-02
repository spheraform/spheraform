"""Unit tests for SQLAlchemy models."""

import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from spheraform_core.models import (
    Geoserver,
    Dataset,
    DownloadJob,
    Theme,
    ChangeCheck,
    ProviderType,
    HealthStatus,
    DownloadStrategy,
    JobStatus,
    ChangeCheckMethod,
)


@pytest.mark.unit
class TestGeoserverModel:
    """Tests for Geoserver model."""

    def test_create_geoserver(self, db_session: Session):
        """Test creating a geoserver."""
        server = Geoserver(
            name="Test ArcGIS Server",
            base_url="https://services.arcgis.com/test",
            provider_type=ProviderType.ARCGIS,
            health_status=HealthStatus.HEALTHY,
            probe_frequency_hours=24,
            dataset_count=0,
            active_dataset_count=0,
        )
        db_session.add(server)
        db_session.commit()

        assert server.id is not None
        assert server.name == "Test ArcGIS Server"
        assert server.provider_type == ProviderType.ARCGIS
        assert server.health_status == HealthStatus.HEALTHY
        assert server.created_at is not None
        assert server.updated_at is not None

    def test_geoserver_timestamps(self, db_session: Session):
        """Test that timestamps are automatically set."""
        server = Geoserver(
            name="Test Server",
            base_url="https://test.com",
            provider_type=ProviderType.ARCGIS,
        )
        db_session.add(server)
        db_session.commit()
        db_session.refresh(server)

        assert server.created_at is not None
        assert server.updated_at is not None
        assert isinstance(server.created_at, datetime)
        assert isinstance(server.updated_at, datetime)

    def test_geoserver_auth_config(self, db_session: Session):
        """Test storing auth configuration as JSON."""
        server = Geoserver(
            name="Test Server",
            base_url="https://test.com",
            provider_type=ProviderType.ARCGIS,
            auth_config={"type": "api_key", "key": "secret123"},
        )
        db_session.add(server)
        db_session.commit()
        db_session.refresh(server)

        assert server.auth_config == {"type": "api_key", "key": "secret123"}
        assert server.auth_config["type"] == "api_key"

    def test_geoserver_capabilities(self, db_session: Session):
        """Test storing server capabilities."""
        server = Geoserver(
            name="Test Server",
            base_url="https://test.com",
            provider_type=ProviderType.ARCGIS,
            capabilities={
                "max_features_per_request": 2000,
                "supports_pagination": True,
            },
        )
        db_session.add(server)
        db_session.commit()
        db_session.refresh(server)

        assert server.capabilities["max_features_per_request"] == 2000
        assert server.capabilities["supports_pagination"] is True


@pytest.mark.unit
class TestDatasetModel:
    """Tests for Dataset model."""

    def test_create_dataset(self, db_session: Session, sample_geoserver: Geoserver):
        """Test creating a dataset."""
        dataset = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="Test Dataset",
            description="A test dataset",
            keywords=["test", "sample"],
            themes=["hydro", "transport"],
            feature_count=1000,
            access_url="https://services.arcgis.com/test/FeatureServer/0",
            download_strategy=DownloadStrategy.SIMPLE,
            is_active=True,
        )
        db_session.add(dataset)
        db_session.commit()

        assert dataset.id is not None
        assert dataset.geoserver_id == sample_geoserver.id
        assert dataset.name == "Test Dataset"
        assert "test" in dataset.keywords
        assert "hydro" in dataset.themes

    def test_dataset_geoserver_relationship(
        self, db_session: Session, sample_dataset: Dataset
    ):
        """Test relationship between dataset and geoserver."""
        db_session.refresh(sample_dataset)
        assert sample_dataset.geoserver is not None
        assert sample_dataset.geoserver.name == "Test ArcGIS Server"

    def test_dataset_keywords_array(self, db_session: Session, sample_geoserver: Geoserver):
        """Test that keywords are stored as array."""
        dataset = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="1",
            name="Keywords Test",
            keywords=["water", "hydrology", "rivers"],
            access_url="https://test.com",
        )
        db_session.add(dataset)
        db_session.commit()
        db_session.refresh(dataset)

        assert len(dataset.keywords) == 3
        assert "water" in dataset.keywords
        assert "hydrology" in dataset.keywords

    def test_dataset_flags(self, db_session: Session, sample_geoserver: Geoserver):
        """Test dataset boolean flags."""
        dataset = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="2",
            name="Flags Test",
            access_url="https://test.com",
            is_cached=True,
            change_detected=True,
            has_geometry_errors=False,
            is_active=True,
        )
        db_session.add(dataset)
        db_session.commit()
        db_session.refresh(dataset)

        assert dataset.is_cached is True
        assert dataset.change_detected is True
        assert dataset.has_geometry_errors is False
        assert dataset.is_active is True


@pytest.mark.unit
class TestThemeModel:
    """Tests for Theme model."""

    def test_create_theme(self, db_session: Session):
        """Test creating a theme."""
        theme = Theme(
            code="hydro",
            name="Hydrology",
            description="Water-related datasets",
            aliases=["water", "stream", "river"],
        )
        db_session.add(theme)
        db_session.commit()

        assert theme.id is not None
        assert theme.code == "hydro"
        assert theme.name == "Hydrology"
        assert "water" in theme.aliases

    def test_theme_hierarchy(self, db_session: Session):
        """Test hierarchical theme relationships."""
        parent = Theme(code="transport", name="Transportation")
        db_session.add(parent)
        db_session.commit()

        child = Theme(
            code="roads",
            name="Roads",
            parent_id=parent.id,
        )
        db_session.add(child)
        db_session.commit()
        db_session.refresh(parent)
        db_session.refresh(child)

        assert child.parent_id == parent.id
        assert child.parent.code == "transport"
        assert len(parent.children) == 1
        assert parent.children[0].code == "roads"


@pytest.mark.unit
class TestDownloadJobModel:
    """Tests for DownloadJob model."""

    def test_create_download_job(self, db_session: Session, sample_dataset: Dataset):
        """Test creating a download job."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.PENDING,
            format="geojson",
            total_chunks=1,
            completed_chunks=0,
        )
        db_session.add(job)
        db_session.commit()

        assert job.id is not None
        assert job.dataset_id == sample_dataset.id
        assert job.status == JobStatus.PENDING
        assert job.format == "geojson"

    def test_download_job_progress(self, db_session: Session, sample_dataset: Dataset):
        """Test job progress tracking."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.IN_PROGRESS,
            format="geojson",
            total_chunks=10,
            completed_chunks=3,
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        # Progress is 30%
        assert job.total_chunks == 10
        assert job.completed_chunks == 3

    def test_download_job_dataset_relationship(
        self, db_session: Session, sample_dataset: Dataset
    ):
        """Test relationship between job and dataset."""
        job = DownloadJob(
            dataset_id=sample_dataset.id,
            status=JobStatus.PENDING,
            format="geojson",
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        assert job.dataset is not None
        assert job.dataset.name == sample_dataset.name


@pytest.mark.unit
class TestChangeCheckModel:
    """Tests for ChangeCheck model."""

    def test_create_change_check(self, db_session: Session, sample_dataset: Dataset):
        """Test creating a change check record."""
        check = ChangeCheck(
            dataset_id=sample_dataset.id,
            method=ChangeCheckMethod.ETAG,
            changed=False,
            conclusive=True,
            cached_etag="abc123",
            current_etag="abc123",
        )
        db_session.add(check)
        db_session.commit()

        assert check.id is not None
        assert check.dataset_id == sample_dataset.id
        assert check.method == ChangeCheckMethod.ETAG
        assert check.changed is False
        assert check.conclusive is True

    def test_change_check_methods(self, db_session: Session, sample_dataset: Dataset):
        """Test different change check methods."""
        methods = [
            ChangeCheckMethod.ETAG,
            ChangeCheckMethod.LAST_MODIFIED,
            ChangeCheckMethod.PROVIDER_METADATA,
        ]

        for method in methods:
            check = ChangeCheck(
                dataset_id=sample_dataset.id,
                method=method,
                changed=False,
                conclusive=True,
            )
            db_session.add(check)

        db_session.commit()

        checks = db_session.query(ChangeCheck).filter_by(dataset_id=sample_dataset.id).all()
        assert len(checks) == 3
        assert all(c.method in methods for c in checks)
