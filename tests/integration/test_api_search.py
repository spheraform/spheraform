"""Integration tests for search API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from geoalchemy2 import WKTElement

from spheraform_core.models import Dataset, DownloadStrategy


@pytest.mark.integration
class TestSearchAPI:
    """Tests for /search endpoint."""

    def test_search_empty_database(self, client: TestClient):
        """Test searching when no datasets exist."""
        search_request = {"query": "water"}

        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["results"]) == 0

    def test_search_by_text_in_name(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test text search in dataset names."""
        # Create datasets with different names
        dataset1 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="Water Resources",
            access_url="https://test.com/0",
        )
        dataset2 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="1",
            name="Transportation Network",
            access_url="https://test.com/1",
        )
        db_session.add_all([dataset1, dataset2])
        db_session.commit()

        search_request = {"query": "water"}

        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "Water Resources"

    def test_search_by_text_case_insensitive(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test that text search is case-insensitive."""
        dataset = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="WATER Resources",
            access_url="https://test.com/0",
        )
        db_session.add(dataset)
        db_session.commit()

        search_request = {"query": "water"}

        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_search_by_text_in_description(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test text search in descriptions."""
        dataset = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="Dataset",
            description="This dataset contains water quality data",
            access_url="https://test.com/0",
        )
        db_session.add(dataset)
        db_session.commit()

        search_request = {"query": "water quality"}

        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_search_by_text_in_keywords(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test text search in keywords."""
        dataset = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="Dataset",
            keywords=["hydrology", "rivers", "watersheds"],
            access_url="https://test.com/0",
        )
        db_session.add(dataset)
        db_session.commit()

        search_request = {"query": "hydrology"}

        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_search_by_themes(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test filtering by themes."""
        dataset1 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="Hydrology Data",
            themes=["hydro", "environment"],
            access_url="https://test.com/0",
        )
        dataset2 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="1",
            name="Road Network",
            themes=["transport"],
            access_url="https://test.com/1",
        )
        db_session.add_all([dataset1, dataset2])
        db_session.commit()

        search_request = {"themes": ["hydro"]}

        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "Hydrology Data"

    def test_search_by_multiple_themes(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test filtering by multiple themes (OR logic)."""
        dataset1 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="Hydrology Data",
            themes=["hydro"],
            access_url="https://test.com/0",
        )
        dataset2 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="1",
            name="Road Network",
            themes=["transport"],
            access_url="https://test.com/1",
        )
        dataset3 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="2",
            name="Administrative Boundaries",
            themes=["admin"],
            access_url="https://test.com/2",
        )
        db_session.add_all([dataset1, dataset2, dataset3])
        db_session.commit()

        search_request = {"themes": ["hydro", "transport"]}

        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        names = [r["name"] for r in data["results"]]
        assert "Hydrology Data" in names
        assert "Road Network" in names

    def test_search_by_bbox(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test spatial search by bounding box."""
        # Dataset in San Francisco area
        dataset1 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="SF Data",
            bbox=WKTElement("POLYGON((-122.5 37.7, -122.5 37.9, -122.3 37.9, -122.3 37.7, -122.5 37.7))", srid=4326),
            access_url="https://test.com/0",
        )
        # Dataset in New York area
        dataset2 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="1",
            name="NYC Data",
            bbox=WKTElement("POLYGON((-74.1 40.6, -74.1 40.8, -73.9 40.8, -73.9 40.6, -74.1 40.6))", srid=4326),
            access_url="https://test.com/1",
        )
        db_session.add_all([dataset1, dataset2])
        db_session.commit()

        # Search for datasets intersecting SF area
        search_request = {
            "bbox": [-122.6, 37.6, -122.2, 38.0]
        }

        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "SF Data"

    def test_search_by_geometry(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test spatial search by GeoJSON geometry."""
        dataset = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="SF Data",
            bbox=WKTElement("POLYGON((-122.5 37.7, -122.5 37.9, -122.3 37.9, -122.3 37.7, -122.5 37.7))", srid=4326),
            access_url="https://test.com/0",
        )
        db_session.add(dataset)
        db_session.commit()

        # Point in SF
        search_request = {
            "geometry": {
                "type": "Point",
                "coordinates": [-122.4, 37.8]
            }
        }

        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_search_combined_filters(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test combining multiple search filters."""
        dataset1 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="Water Resources SF",
            themes=["hydro"],
            bbox=WKTElement("POLYGON((-122.5 37.7, -122.5 37.9, -122.3 37.9, -122.3 37.7, -122.5 37.7))", srid=4326),
            access_url="https://test.com/0",
        )
        dataset2 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="1",
            name="Water Resources NYC",
            themes=["hydro"],
            bbox=WKTElement("POLYGON((-74.1 40.6, -74.1 40.8, -73.9 40.8, -73.9 40.6, -74.1 40.6))", srid=4326),
            access_url="https://test.com/1",
        )
        dataset3 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="2",
            name="Roads SF",
            themes=["transport"],
            bbox=WKTElement("POLYGON((-122.5 37.7, -122.5 37.9, -122.3 37.9, -122.3 37.7, -122.5 37.7))", srid=4326),
            access_url="https://test.com/2",
        )
        db_session.add_all([dataset1, dataset2, dataset3])
        db_session.commit()

        # Search for hydro datasets in SF area
        search_request = {
            "query": "water",
            "themes": ["hydro"],
            "bbox": [-122.6, 37.6, -122.2, 38.0]
        }

        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "Water Resources SF"

    def test_search_pagination(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test search result pagination."""
        # Create 25 datasets
        for i in range(25):
            dataset = Dataset(
                geoserver_id=sample_geoserver.id,
                external_id=str(i),
                name=f"Dataset {i}",
                access_url=f"https://test.com/{i}",
            )
            db_session.add(dataset)
        db_session.commit()

        # Get first page
        search_request = {"limit": 10, "offset": 0}
        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 25
        assert len(data["results"]) == 10

        # Get second page
        search_request = {"limit": 10, "offset": 10}
        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 25
        assert len(data["results"]) == 10

    def test_search_facets(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test search result facets."""
        # Create datasets with different themes
        dataset1 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="0",
            name="Dataset 1",
            themes=["hydro"],
            access_url="https://test.com/0",
        )
        dataset2 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="1",
            name="Dataset 2",
            themes=["hydro", "environment"],
            access_url="https://test.com/1",
        )
        dataset3 = Dataset(
            geoserver_id=sample_geoserver.id,
            external_id="2",
            name="Dataset 3",
            themes=["transport"],
            access_url="https://test.com/2",
        )
        db_session.add_all([dataset1, dataset2, dataset3])
        db_session.commit()

        search_request = {}

        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert "facets" in data
        assert "themes" in data["facets"]

        # Check theme counts
        theme_facets = {f["value"]: f["count"] for f in data["facets"]["themes"]}
        assert theme_facets.get("hydro") == 2
        assert theme_facets.get("environment") == 1
        assert theme_facets.get("transport") == 1

    def test_search_only_active_datasets(
        self, client: TestClient, db_session: Session, sample_geoserver
    ):
        """Test that search only returns active datasets by default."""
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

        search_request = {}

        response = client.post("/search/", json=search_request)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "Active Dataset"
