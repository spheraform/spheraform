"""Test GeoParquet read/write round-trip to ensure coordinate integrity."""

import json
import struct
import tempfile
from pathlib import Path

import pytest

from spheraform_core.storage.geoparquet import (
    geojson_to_geoparquet,
    geoparquet_to_geojson,
)
from spheraform_core.storage.pmtiles_gen import generate_from_geojson


class TestGeoParquetRoundTrip:
    """Test that coordinates are preserved through GeoParquet conversion."""

    def test_point_coordinates_preserved(self):
        """Test that point coordinates in Scotland are preserved."""
        # Create test GeoJSON with Scotland coordinates
        test_coords = [-4.5, 57.5]  # Somewhere in Scotland
        test_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": test_coords},
                    "properties": {"name": "Test Point"},
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Write GeoJSON
            geojson_path = tmpdir / "test.geojson"
            with open(geojson_path, "w") as f:
                json.dump(test_geojson, f)

            # Convert to GeoParquet
            parquet_path = tmpdir / "test.parquet"
            geojson_to_geoparquet(geojson_path, parquet_path)

            # Convert back to GeoJSON
            geojson_out_path = tmpdir / "test_out.geojson"
            geoparquet_to_geojson(parquet_path, geojson_out_path)

            # Read output
            with open(geojson_out_path, "r") as f:
                output_geojson = json.load(f)

            # Check coordinates match (within reasonable tolerance)
            output_coords = output_geojson["features"][0]["geometry"]["coordinates"]
            assert abs(output_coords[0] - test_coords[0]) < 1e-6, (
                f"Longitude mismatch: expected {test_coords[0]}, "
                f"got {output_coords[0]}"
            )
            assert abs(output_coords[1] - test_coords[1]) < 1e-6, (
                f"Latitude mismatch: expected {test_coords[1]}, "
                f"got {output_coords[1]}"
            )

    def test_polygon_coordinates_preserved(self):
        """Test that polygon coordinates are preserved."""
        # Scotland bounding box
        test_polygon = [
            [
                [-6.5, 56.5],
                [-3.5, 56.5],
                [-3.5, 59.0],
                [-6.5, 59.0],
                [-6.5, 56.5],
            ]
        ]

        test_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": test_polygon},
                    "properties": {"name": "Scotland Box"},
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            geojson_path = tmpdir / "test.geojson"
            with open(geojson_path, "w") as f:
                json.dump(test_geojson, f)

            parquet_path = tmpdir / "test.parquet"
            geojson_to_geoparquet(geojson_path, parquet_path)

            geojson_out_path = tmpdir / "test_out.geojson"
            geoparquet_to_geojson(parquet_path, geojson_out_path)

            with open(geojson_out_path, "r") as f:
                output_geojson = json.load(f)

            output_coords = output_geojson["features"][0]["geometry"]["coordinates"][0]

            # Check first and last points match
            for i, expected_point in enumerate([test_polygon[0][0], test_polygon[0][-1]]):
                output_point = output_coords[i]
                assert abs(output_point[0] - expected_point[0]) < 1e-6
                assert abs(output_point[1] - expected_point[1]) < 1e-6


class TestPMTilesGeneration:
    """Test that PMTiles generation produces correct bounds."""

    def test_pmtiles_bounds_match_geojson(self):
        """Test that PMTiles bounds match the input GeoJSON bounds."""
        # Create GeoJSON with known bounds
        scotland_coords = [
            [
                [-6.0, 57.0],
                [-4.0, 57.0],
                [-4.0, 58.0],
                [-6.0, 58.0],
                [-6.0, 57.0],
            ]
        ]

        test_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": scotland_coords},
                    "properties": {"name": "Test"},
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Write GeoJSON
            geojson_path = tmpdir / "test.geojson"
            with open(geojson_path, "w") as f:
                json.dump(test_geojson, f)

            # Generate PMTiles
            pmtiles_path = tmpdir / "test.pmtiles"
            generate_from_geojson(
                geojson_path,
                pmtiles_path,
                layer_name="test",
                min_zoom=0,
                max_zoom=10,
            )

            # Read PMTiles bounds from header
            with open(pmtiles_path, "rb") as f:
                header = f.read(127)

                # Parse bounds (offset 36-52, 4 int32 values in 1e7 format)
                min_lon_e7 = struct.unpack("<i", header[36:40])[0]
                min_lat_e7 = struct.unpack("<i", header[40:44])[0]
                max_lon_e7 = struct.unpack("<i", header[44:48])[0]
                max_lat_e7 = struct.unpack("<i", header[48:52])[0]

                pmtiles_bounds = [
                    min_lon_e7 / 1e7,
                    min_lat_e7 / 1e7,
                    max_lon_e7 / 1e7,
                    max_lat_e7 / 1e7,
                ]

            # Expected bounds from GeoJSON
            expected_bounds = [-6.0, 57.0, -4.0, 58.0]

            # Check bounds match (with tolerance for tippecanoe processing)
            assert abs(pmtiles_bounds[0] - expected_bounds[0]) < 0.1, (
                f"Min longitude mismatch: expected {expected_bounds[0]}, "
                f"got {pmtiles_bounds[0]}"
            )
            assert abs(pmtiles_bounds[1] - expected_bounds[1]) < 0.1, (
                f"Min latitude mismatch: expected {expected_bounds[1]}, "
                f"got {pmtiles_bounds[1]}"
            )
            assert abs(pmtiles_bounds[2] - expected_bounds[2]) < 0.1, (
                f"Max longitude mismatch: expected {expected_bounds[2]}, "
                f"got {pmtiles_bounds[2]}"
            )
            assert abs(pmtiles_bounds[3] - expected_bounds[3]) < 0.1, (
                f"Max latitude mismatch: expected {expected_bounds[3]}, "
                f"got {pmtiles_bounds[3]}"
            )

            # Additional check: bounds should NOT be near (0,0)
            assert not (
                abs(pmtiles_bounds[0]) < 0.01
                and abs(pmtiles_bounds[1]) < 0.01
                and abs(pmtiles_bounds[2]) < 0.01
                and abs(pmtiles_bounds[3]) < 0.01
            ), f"PMTiles bounds are near (0,0): {pmtiles_bounds}"

    def test_pmtiles_bounds_not_web_mercator(self):
        """Test that PMTiles bounds are in WGS84, not Web Mercator."""
        # Scotland point
        test_coords = [-4.5, 57.5]

        test_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": test_coords},
                    "properties": {"name": "Test"},
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            geojson_path = tmpdir / "test.geojson"
            with open(geojson_path, "w") as f:
                json.dump(test_geojson, f)

            pmtiles_path = tmpdir / "test.pmtiles"
            generate_from_geojson(geojson_path, pmtiles_path, layer_name="test")

            with open(pmtiles_path, "rb") as f:
                header = f.read(127)
                min_lon_e7 = struct.unpack("<i", header[36:40])[0]
                min_lat_e7 = struct.unpack("<i", header[40:44])[0]

                pmtiles_min_lon = min_lon_e7 / 1e7
                pmtiles_min_lat = min_lat_e7 / 1e7

            # WGS84 coordinates should be in range [-180, 180] for lon, [-90, 90] for lat
            assert -180 <= pmtiles_min_lon <= 180, (
                f"Longitude {pmtiles_min_lon} is outside WGS84 range"
            )
            assert -90 <= pmtiles_min_lat <= 90, (
                f"Latitude {pmtiles_min_lat} is outside WGS84 range"
            )

            # Web Mercator coordinates for this location would be around -500000, 7800000
            # If we see values like that, the coordinates are in Web Mercator
            assert abs(pmtiles_min_lon) < 200, (
                f"Longitude {pmtiles_min_lon} looks like Web Mercator, not WGS84"
            )
