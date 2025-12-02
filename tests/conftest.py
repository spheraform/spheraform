"""Pytest configuration and fixtures."""

import pytest
import pytest_asyncio
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

# Disable GeoAlchemy2 admin functions for SQLite testing
# Must be done before importing models
from geoalchemy2 import admin
# Monkey-patch admin functions to no-op
admin.dialects.sqlite.after_create = lambda *args, **kwargs: None
admin.dialects.sqlite.before_drop = lambda *args, **kwargs: None

from spheraform_core.models.base import Base
from spheraform_core.models import Geoserver, Dataset, DownloadJob, Theme
from spheraform_api.main import app
from spheraform_api.dependencies import get_db


# Test database URL (in-memory SQLite for speed)
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    """Create test database engine."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """Create a new database session for each test."""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    session = TestingSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session: Session):
    """Create test client with overridden database dependency."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# Sample data fixtures


@pytest.fixture
def sample_geoserver(db_session: Session) -> Geoserver:
    """Create a sample geoserver for testing."""
    from spheraform_core.models import ProviderType, HealthStatus

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
    db_session.refresh(server)
    return server


@pytest.fixture
def sample_dataset(db_session: Session, sample_geoserver: Geoserver) -> Dataset:
    """Create a sample dataset for testing."""
    from spheraform_core.models import DownloadStrategy

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
        is_cached=False,
        change_detected=False,
        has_geometry_errors=False,
        is_active=True,
        # Note: bbox (geometry) is set to None for SQLite testing
        bbox=None,
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset


@pytest.fixture
def sample_themes(db_session: Session) -> list[Theme]:
    """Create sample themes for testing."""
    themes = [
        Theme(
            code="hydro",
            name="Hydrology",
            description="Water-related datasets",
            aliases=["water", "stream", "river", "watershed"],
        ),
        Theme(
            code="transport",
            name="Transportation",
            description="Roads, rails, and transit",
            aliases=["road", "highway", "rail", "transit"],
        ),
        Theme(
            code="admin",
            name="Administrative Boundaries",
            description="Political and administrative boundaries",
            aliases=["boundary", "border", "jurisdiction"],
        ),
    ]
    for theme in themes:
        db_session.add(theme)
    db_session.commit()
    for theme in themes:
        db_session.refresh(theme)
    return themes


# Mock HTTP responses for adapter tests


@pytest.fixture
def mock_arcgis_server_info():
    """Mock ArcGIS server root response."""
    return {
        "currentVersion": 10.91,
        "folders": ["SampleFolder"],
        "services": [
            {"name": "SampleWorldCities", "type": "MapServer"},
            {"name": "SampleFeatureService", "type": "FeatureServer"},
        ],
    }


@pytest.fixture
def mock_arcgis_service_info():
    """Mock ArcGIS FeatureServer info response."""
    return {
        "currentVersion": 10.91,
        "serviceDescription": "Sample Feature Service",
        "maxRecordCount": 2000,
        "supportedQueryFormats": "JSON, geoJSON",
        "capabilities": "Query,Extract",
        "layers": [
            {"id": 0, "name": "Points", "type": "Feature Layer"},
            {"id": 1, "name": "Lines", "type": "Feature Layer"},
        ],
    }


@pytest.fixture
def mock_arcgis_layer_info():
    """Mock ArcGIS layer info response."""
    return {
        "id": 0,
        "name": "Cities",
        "type": "Feature Layer",
        "description": "World cities layer",
        "geometryType": "esriGeometryPoint",
        "copyrightText": "Esri",
        "extent": {
            "xmin": -180,
            "ymin": -90,
            "xmax": 180,
            "ymax": 90,
            "spatialReference": {"wkid": 4326},
        },
        "fields": [
            {"name": "OBJECTID", "type": "esriFieldTypeOID"},
            {"name": "CITY_NAME", "type": "esriFieldTypeString"},
            {"name": "POP", "type": "esriFieldTypeInteger"},
        ],
        "editingInfo": {
            "lastEditDate": 1638360000000  # Timestamp in milliseconds
        },
    }


@pytest.fixture
def mock_arcgis_query_response():
    """Mock ArcGIS query response (GeoJSON)."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": 1,
                "geometry": {"type": "Point", "coordinates": [-122.4, 37.8]},
                "properties": {"OBJECTID": 1, "CITY_NAME": "San Francisco", "POP": 883305},
            },
            {
                "type": "Feature",
                "id": 2,
                "geometry": {"type": "Point", "coordinates": [-118.2, 34.0]},
                "properties": {"OBJECTID": 2, "CITY_NAME": "Los Angeles", "POP": 3979576},
            },
        ],
    }


@pytest.fixture
def mock_arcgis_count_response():
    """Mock ArcGIS count query response."""
    return {"count": 1000}


@pytest.fixture
def mock_arcgis_oid_range_response():
    """Mock ArcGIS OID range statistics response."""
    return {
        "features": [
            {
                "attributes": {
                    "MIN_OID": 1,
                    "MAX_OID": 1000,
                }
            }
        ]
    }
