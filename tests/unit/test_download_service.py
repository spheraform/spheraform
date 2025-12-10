"""Unit tests for download service cancellation logic."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from sqlalchemy.orm import Session

from spheraform_core.models import Dataset, Geoserver, DownloadJob, JobStatus, DownloadStrategy, ProviderType, HealthStatus
from spheraform_api.services.download import DownloadService


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = Mock(spec=Session)
    return session


@pytest.fixture
def mock_dataset():
    """Create a mock dataset."""
    dataset = Mock(spec=Dataset)
    dataset.id = "test-dataset-id"
    dataset.name = "Test Dataset"
    dataset.access_url = "https://test.com/FeatureServer/0"
    dataset.download_strategy = DownloadStrategy.SIMPLE
    dataset.geoserver_id = "test-server-id"
    return dataset


@pytest.fixture
def mock_geoserver():
    """Create a mock geoserver."""
    server = Mock(spec=Geoserver)
    server.id = "test-server-id"
    server.base_url = "https://test.com"
    server.provider_type = ProviderType.ARCGIS
    server.health_status = HealthStatus.HEALTHY
    server.country = "US"
    return server


@pytest.mark.unit
class TestDownloadServiceCancellation:
    """Tests for download service cancellation logic."""

    def test_store_in_postgis_checks_cancellation(
        self, mock_db_session, mock_dataset, mock_geoserver
    ):
        """Test that _store_in_postgis checks for cancellation."""
        service = DownloadService(mock_db_session)

        # Create a mock job that gets cancelled
        mock_job = Mock(spec=DownloadJob)
        mock_job.id = "test-job-id"
        mock_job.status = JobStatus.RUNNING

        # On second query (after first batch), job is cancelled
        call_count = [0]

        def query_side_effect(*args, **kwargs):
            # Return a mock query object
            query_mock = Mock()
            query_mock.filter.return_value.first.return_value = mock_job

            call_count[0] += 1
            # Cancel after first batch (call_count > 2: initial set + first batch check)
            if call_count[0] > 2:
                mock_job.status = JobStatus.CANCELLED

            return query_mock

        mock_db_session.query.side_effect = query_side_effect
        mock_db_session.execute.return_value = None

        # Create mock GeoJSON data with multiple features (more than batch size)
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-122.4, 37.8]},
                    "properties": {"id": i, "name": f"Feature {i}"},
                }
                for i in range(2000)  # More than batch size of 1000
            ],
        }

        # This should detect cancellation and return early
        import asyncio

        asyncio.run(
            service._store_in_postgis(
                cache_table="test_table", geojson_data=geojson_data, job_id=mock_job.id
            )
        )

        # Verify that DROP TABLE was called to clean up
        # Check if any execute call contains DROP TABLE
        # The execute method is called with text(sql), so check args and kwargs
        drop_called = False
        for call in mock_db_session.execute.call_args_list:
            # call is a tuple of (args, kwargs)
            args, kwargs = call
            if args:
                sql_text = str(args[0])
                if "DROP TABLE" in sql_text:
                    drop_called = True
                    break

        assert drop_called, f"DROP TABLE should be called on cancellation. Execute calls: {mock_db_session.execute.call_args_list}"

    def test_store_in_postgis_completes_without_cancellation(
        self, mock_db_session, mock_dataset, mock_geoserver
    ):
        """Test that _store_in_postgis completes when not cancelled."""
        service = DownloadService(mock_db_session)

        # Create a mock job that stays running
        mock_job = Mock(spec=DownloadJob)
        mock_job.id = "test-job-id"
        mock_job.status = JobStatus.RUNNING

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_job
        )
        mock_db_session.execute.return_value = None

        # Create mock GeoJSON data with small number of features
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-122.4, 37.8]},
                    "properties": {"id": 1, "name": "Feature 1"},
                }
            ],
        }

        # This should complete normally
        import asyncio

        asyncio.run(
            service._store_in_postgis(
                cache_table="test_table", geojson_data=geojson_data, job_id=mock_job.id
            )
        )

        # Verify that spatial index was created (not dropped)
        # Check if any execute call contains CREATE INDEX
        create_index_called = False
        for call in mock_db_session.execute.call_args_list:
            # call is a tuple of (args, kwargs)
            args, kwargs = call
            if args:
                sql_text = str(args[0])
                if "CREATE INDEX" in sql_text:
                    create_index_called = True
                    break

        assert (
            create_index_called
        ), f"CREATE INDEX should be called on successful completion. Execute calls: {mock_db_session.execute.call_args_list}"

    def test_store_in_postgis_updates_progress(
        self, mock_db_session, mock_dataset, mock_geoserver
    ):
        """Test that _store_in_postgis updates job progress."""
        service = DownloadService(mock_db_session)

        # Create a mock job
        mock_job = Mock(spec=DownloadJob)
        mock_job.id = "test-job-id"
        mock_job.status = JobStatus.RUNNING
        mock_job.features_stored = 0

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_job
        )
        mock_db_session.execute.return_value = None

        # Create mock GeoJSON data
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-122.4, 37.8]},
                    "properties": {"id": i, "name": f"Feature {i}"},
                }
                for i in range(1500)  # 1.5 batches
            ],
        }

        # This should update progress
        import asyncio

        asyncio.run(
            service._store_in_postgis(
                cache_table="test_table", geojson_data=geojson_data, job_id=mock_job.id
            )
        )

        # Verify that features_stored was updated
        assert mock_job.features_stored > 0, "features_stored should be updated"

    def test_store_in_postgis_sets_stage_to_storing(
        self, mock_db_session, mock_dataset, mock_geoserver
    ):
        """Test that _store_in_postgis sets job stage to 'storing'."""
        service = DownloadService(mock_db_session)

        # Create a mock job and track stage changes
        mock_job = Mock(spec=DownloadJob)
        mock_job.id = "test-job-id"
        mock_job.status = JobStatus.RUNNING
        mock_job.current_stage = None

        # Track all stage changes
        stage_history = []

        def track_stage_change(value):
            stage_history.append(value)

        type(mock_job).current_stage = property(
            lambda self: self._current_stage,
            lambda self, value: track_stage_change(value) or setattr(self, '_current_stage', value)
        )
        mock_job._current_stage = None

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_job
        )
        mock_db_session.execute.return_value = None

        # Create mock GeoJSON data
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-122.4, 37.8]},
                    "properties": {"id": 1, "name": "Feature 1"},
                }
            ],
        }

        # This should set stage
        import asyncio

        asyncio.run(
            service._store_in_postgis(
                cache_table="test_table", geojson_data=geojson_data, job_id=mock_job.id
            )
        )

        # Verify that current_stage was set to 'storing' at some point
        assert "storing" in stage_history, f"Stage should be set to 'storing' (history: {stage_history})"

    def test_store_in_postgis_sets_stage_to_indexing(
        self, mock_db_session, mock_dataset, mock_geoserver
    ):
        """Test that _store_in_postgis sets job stage to 'indexing'."""
        service = DownloadService(mock_db_session)

        # Create a mock job
        mock_job = Mock(spec=DownloadJob)
        mock_job.id = "test-job-id"
        mock_job.status = JobStatus.RUNNING
        mock_job.current_stage = "storing"

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_job
        )
        mock_db_session.execute.return_value = None

        # Create mock GeoJSON data
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-122.4, 37.8]},
                    "properties": {"id": 1, "name": "Feature 1"},
                }
            ],
        }

        # This should set stage to indexing
        import asyncio

        asyncio.run(
            service._store_in_postgis(
                cache_table="test_table", geojson_data=geojson_data, job_id=mock_job.id
            )
        )

        # Verify that current_stage was updated to indexing
        assert (
            mock_job.current_stage == "indexing"
        ), "Stage should be set to 'indexing' before creating index"

    def test_store_in_postgis_batch_size_1000(
        self, mock_db_session, mock_dataset, mock_geoserver
    ):
        """Test that _store_in_postgis processes in batches of 1000."""
        service = DownloadService(mock_db_session)

        # Create a mock job
        mock_job = Mock(spec=DownloadJob)
        mock_job.id = "test-job-id"
        mock_job.status = JobStatus.RUNNING

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_job
        )
        mock_db_session.execute.return_value = None

        # Create mock GeoJSON data with 2500 features (2.5 batches)
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-122.4, 37.8]},
                    "properties": {"id": i, "name": f"Feature {i}"},
                }
                for i in range(2500)
            ],
        }

        # This should process in batches
        import asyncio

        asyncio.run(
            service._store_in_postgis(
                cache_table="test_table", geojson_data=geojson_data, job_id=mock_job.id
            )
        )

        # Verify that progress was updated at least 3 times (1000, 2000, 2500)
        # This is a proxy for checking batch processing
        commit_count = mock_db_session.commit.call_count
        assert commit_count >= 3, "Should commit after each batch"
