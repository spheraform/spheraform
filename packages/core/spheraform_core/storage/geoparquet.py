"""GeoParquet format conversion utilities."""

import json
import logging
from pathlib import Path
from typing import Optional, Iterator
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq
import fiona
from shapely.geometry import shape, mapping
from shapely.ops import transform
import pyproj

logger = logging.getLogger(__name__)

# Batch size for streaming large datasets
BATCH_SIZE = 10_000

# Threshold for streaming (features count)
STREAMING_THRESHOLD = 100_000


def geojson_to_geoparquet(
    geojson_path: str | Path,
    parquet_path: str | Path,
    compression: str = "snappy",
    batch_size: int = BATCH_SIZE,
) -> dict:
    """
    Convert GeoJSON to GeoParquet format.

    Uses streaming for large datasets to avoid memory issues.
    Stores in EPSG:4326 for interoperability.

    Args:
        geojson_path: Path to input GeoJSON file
        parquet_path: Path to output Parquet file
        compression: Compression algorithm (snappy, gzip, zstd)
        batch_size: Number of features per batch for streaming

    Returns:
        Dict with metadata (num_features, size_bytes, schema)
    """
    geojson_path = Path(geojson_path)
    parquet_path = Path(parquet_path)

    logger.info(f"Converting {geojson_path} to GeoParquet")

    # Create parent directory if needed
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    # Read GeoJSON and convert to GeoParquet using Fiona for streaming
    # Set OGR_GEOJSON_MAX_OBJ_SIZE to 0 to remove size limit for large GeoJSON files
    with fiona.Env(OGR_GEOJSON_MAX_OBJ_SIZE=0):
        with fiona.open(geojson_path, "r") as src:
            total_features = len(src)
            logger.info(f"Converting {total_features} features to GeoParquet")

            # Get CRS and schema
            crs = src.crs
            if crs:
                # Fiona CRS is a CRS object, not a dict
                source_crs = crs.to_string() if hasattr(crs, 'to_string') else str(crs)
            else:
                source_crs = "EPSG:4326"

            # Setup reprojection to EPSG:4326 if needed
            if source_crs.lower() != "epsg:4326":
                logger.info(f"Reprojecting from {source_crs} to EPSG:4326")
                project = pyproj.Transformer.from_crs(
                    source_crs, "EPSG:4326", always_xy=True
                ).transform
            else:
                project = None

            # Build schema from first feature
            first_feature = next(iter(src))
            schema = _build_arrow_schema(first_feature)

            # Determine if we should stream
            use_streaming = total_features > STREAMING_THRESHOLD

            if use_streaming:
                logger.info(f"Using streaming mode (batch_size={batch_size})")
                _write_parquet_streaming(
                    src, parquet_path, schema, compression, batch_size, project
                )
            else:
                logger.info("Using in-memory conversion")
                _write_parquet_inmemory(
                    src, parquet_path, schema, compression, project
                )

    # Get file size
    size_bytes = parquet_path.stat().st_size

    logger.info(f"GeoParquet written: {parquet_path} ({size_bytes} bytes)")

    return {
        "num_features": total_features,
        "size_bytes": size_bytes,
        "schema": json.dumps([{"name": field.name, "type": str(field.type)} for field in schema]),
    }


def _build_arrow_schema(feature: dict) -> pa.Schema:
    """Build Arrow schema from GeoJSON feature."""
    fields = []

    # Add geometry column (WKB format)
    fields.append(pa.field("geometry", pa.binary()))

    # Add properties columns
    if "properties" in feature and feature["properties"]:
        for key, value in feature["properties"].items():
            # Infer type from value
            if value is None:
                field_type = pa.string()
            elif isinstance(value, bool):
                field_type = pa.bool_()
            elif isinstance(value, int):
                field_type = pa.int64()
            elif isinstance(value, float):
                field_type = pa.float64()
            else:
                field_type = pa.string()

            fields.append(pa.field(key, field_type))

    return pa.schema(fields)


def _write_parquet_streaming(
    src: fiona.Collection,
    parquet_path: Path,
    schema: pa.Schema,
    compression: str,
    batch_size: int,
    project: Optional[callable] = None,
) -> None:
    """Write GeoParquet using streaming (batches)."""
    writer = None

    try:
        for batch_records in _batch_iterator(src, batch_size):
            # Convert batch to Arrow table
            table = _records_to_arrow_table(batch_records, schema, project)

            # Create writer on first batch
            if writer is None:
                # Add GeoParquet metadata to schema for first batch
                table = _add_geoparquet_metadata(table)

                writer = pq.ParquetWriter(
                    parquet_path,
                    table.schema,
                    compression=compression,
                    version="2.6",
                )

            # Write batch
            writer.write_table(table)

    finally:
        if writer:
            writer.close()


def _write_parquet_inmemory(
    src: fiona.Collection,
    parquet_path: Path,
    schema: pa.Schema,
    compression: str,
    project: Optional[callable] = None,
) -> None:
    """Write GeoParquet in-memory (all features at once)."""
    records = list(src)
    table = _records_to_arrow_table(records, schema, project)

    # Add GeoParquet metadata to schema
    table = _add_geoparquet_metadata(table)

    pq.write_table(
        table,
        parquet_path,
        compression=compression,
        version="2.6",
    )


def _batch_iterator(collection: fiona.Collection, batch_size: int) -> Iterator[list]:
    """Iterate over Fiona collection in batches."""
    batch = []
    for record in collection:
        batch.append(record)
        if len(batch) >= batch_size:
            yield batch
            batch = []

    if batch:
        yield batch


def _records_to_arrow_table(
    records: list[dict],
    schema: pa.Schema,
    project: Optional[callable] = None,
) -> pa.Table:
    """Convert Fiona records to Arrow table."""
    from shapely import wkb

    columns = {field.name: [] for field in schema}

    for record in records:
        # Convert geometry to WKB
        geom = shape(record["geometry"])

        # Reproject if needed
        if project:
            geom = transform(project, geom)

        columns["geometry"].append(wkb.dumps(geom))

        # Add properties
        properties = record.get("properties", {})
        for field in schema:
            if field.name == "geometry":
                continue

            value = properties.get(field.name)

            # Handle None/null
            if value is None:
                columns[field.name].append(None)
            # Convert to proper type
            elif field.type == pa.bool_():
                columns[field.name].append(bool(value))
            elif field.type == pa.int64():
                columns[field.name].append(int(value))
            elif field.type == pa.float64():
                columns[field.name].append(float(value))
            else:
                columns[field.name].append(str(value))

    # Create Arrow arrays
    arrays = []
    for field in schema:
        arrays.append(pa.array(columns[field.name], type=field.type))

    return pa.Table.from_arrays(arrays, schema=schema)


def _add_geoparquet_metadata(table: pa.Table) -> pa.Table:
    """
    Add GeoParquet metadata to table schema.

    Adds the required 'geo' metadata field to make the Parquet file
    compliant with the GeoParquet v1.0.0 specification.

    Args:
        table: Arrow table with geometry column

    Returns:
        Table with GeoParquet metadata in schema
    """
    from shapely import wkb

    # Calculate bbox and detect geometry types from all geometries
    min_x, min_y, max_x, max_y = float('inf'), float('inf'), float('-inf'), float('-inf')
    geometry_types = set()

    for i in range(len(table)):
        geom_wkb_bytes = table["geometry"][i].as_py()
        if geom_wkb_bytes:
            geom = wkb.loads(geom_wkb_bytes)
            geometry_types.add(geom.geom_type)

            # Update bbox
            bounds = geom.bounds
            min_x = min(min_x, bounds[0])
            min_y = min(min_y, bounds[1])
            max_x = max(max_x, bounds[2])
            max_y = max(max_y, bounds[3])

    # Build GeoParquet metadata per v1.0.0 spec
    # Use PROJJSON format for CRS (compatible with pyproj/GeoPandas)
    geo_metadata = {
        "version": "1.0.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                "geometry_types": sorted(list(geometry_types)),
                "crs": {
                    "$schema": "https://proj.org/schemas/v0.4/projjson.schema.json",
                    "type": "GeographicCRS",
                    "name": "WGS 84",
                    "datum_ensemble": {
                        "name": "World Geodetic System 1984 ensemble",
                        "members": [
                            {
                                "name": "World Geodetic System 1984 (Transit)",
                                "id": {
                                    "authority": "EPSG",
                                    "code": 1166
                                }
                            },
                            {
                                "name": "World Geodetic System 1984 (G730)",
                                "id": {
                                    "authority": "EPSG",
                                    "code": 1152
                                }
                            },
                            {
                                "name": "World Geodetic System 1984 (G873)",
                                "id": {
                                    "authority": "EPSG",
                                    "code": 1153
                                }
                            },
                            {
                                "name": "World Geodetic System 1984 (G1150)",
                                "id": {
                                    "authority": "EPSG",
                                    "code": 1154
                                }
                            },
                            {
                                "name": "World Geodetic System 1984 (G1674)",
                                "id": {
                                    "authority": "EPSG",
                                    "code": 1155
                                }
                            },
                            {
                                "name": "World Geodetic System 1984 (G1762)",
                                "id": {
                                    "authority": "EPSG",
                                    "code": 1156
                                }
                            },
                            {
                                "name": "World Geodetic System 1984 (G2139)",
                                "id": {
                                    "authority": "EPSG",
                                    "code": 1309
                                }
                            }
                        ],
                        "ellipsoid": {
                            "name": "WGS 84",
                            "semi_major_axis": 6378137,
                            "inverse_flattening": 298.257223563
                        },
                        "accuracy": "2.0",
                        "id": {
                            "authority": "EPSG",
                            "code": 6326
                        }
                    },
                    "coordinate_system": {
                        "subtype": "ellipsoidal",
                        "axis": [
                            {
                                "name": "Geodetic latitude",
                                "abbreviation": "Lat",
                                "direction": "north",
                                "unit": "degree"
                            },
                            {
                                "name": "Geodetic longitude",
                                "abbreviation": "Lon",
                                "direction": "east",
                                "unit": "degree"
                            }
                        ]
                    },
                    "scope": "Horizontal component of 3D system.",
                    "area": "World.",
                    "bbox": {
                        "south_latitude": -90,
                        "west_longitude": -180,
                        "north_latitude": 90,
                        "east_longitude": 180
                    },
                    "id": {
                        "authority": "EPSG",
                        "code": 4326
                    }
                },
                "bbox": [min_x, min_y, max_x, max_y]
            }
        }
    }

    # Add metadata to schema
    existing_metadata = table.schema.metadata or {}
    new_metadata = {
        **existing_metadata,
        b'geo': json.dumps(geo_metadata).encode('utf-8')
    }

    # Create new schema with metadata
    new_schema = table.schema.with_metadata(new_metadata)

    # Return table with updated schema
    return table.cast(new_schema)


def geoparquet_to_geojson(
    parquet_path: str | Path,
    geojson_path: str | Path,
    bbox: Optional[tuple[float, float, float, float]] = None,
) -> dict:
    """
    Convert GeoParquet to GeoJSON format.

    Args:
        parquet_path: Path to input Parquet file
        geojson_path: Path to output GeoJSON file
        bbox: Optional bounding box filter (minx, miny, maxx, maxy) in EPSG:4326

    Returns:
        Dict with metadata (num_features, size_bytes)
    """
    from shapely import wkb
    from shapely.geometry import box

    parquet_path = Path(parquet_path)
    geojson_path = Path(geojson_path)

    logger.info(f"Converting {parquet_path} to GeoJSON")

    # Create parent directory if needed
    geojson_path.parent.mkdir(parents=True, exist_ok=True)

    # Read Parquet
    table = pq.read_table(parquet_path)

    # Apply bbox filter if provided
    if bbox:
        logger.info(f"Applying bbox filter: {bbox}")
        bbox_geom = box(*bbox)
        table = _filter_by_bbox(table, bbox_geom)

    num_features = len(table)
    logger.info(f"Converting {num_features} features to GeoJSON")

    # Convert to GeoJSON
    features = []

    # Check if we need to reproject (GeoJSON should always be in EPSG:4326)
    needs_reprojection = False
    source_crs = None

    # Try to get CRS from GeoParquet metadata
    if hasattr(table.schema, 'metadata') and table.schema.metadata:
        geo_metadata = table.schema.metadata.get(b'geo')
        if geo_metadata:
            import json as json_module
            geo_dict = json_module.loads(geo_metadata)
            crs = geo_dict.get('columns', {}).get('geometry', {}).get('crs')
            if crs:
                # Parse CRS - can be string or dict
                if isinstance(crs, dict):
                    # Extract EPSG code from dict format
                    crs_id = crs.get('id', {})
                    if crs_id.get('authority') == 'EPSG':
                        epsg_code = crs_id.get('code')
                        source_crs = f"EPSG:{epsg_code}"
                    else:
                        # Unsupported CRS format
                        source_crs = 'EPSG:4326'
                        logger.warning(f"Unsupported CRS format: {crs}, assuming EPSG:4326")
                else:
                    source_crs = str(crs)

                # Check if we need reprojection
                if source_crs.upper() != 'EPSG:4326':
                    needs_reprojection = True
                    logger.info(f"Reprojecting from {source_crs} to EPSG:4326 for GeoJSON export")
                else:
                    source_crs = 'EPSG:4326'

    # If no metadata, assume EPSG:4326 (WGS84) - this is what we store by default
    if not source_crs:
        # Default assumption: data is stored in EPSG:4326 (no transformation needed)
        needs_reprojection = False
        source_crs = 'EPSG:4326'
        logger.info("No CRS metadata found, assuming data is in EPSG:4326 (no transformation needed)")

    # Create transformer if needed
    transformer = None
    if needs_reprojection:
        from pyproj import Transformer
        transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)

    for i in range(num_features):
        # Parse WKB geometry
        geom_wkb = table["geometry"][i].as_py()
        geom = wkb.loads(geom_wkb)

        # Reproject to EPSG:4326 if needed
        if transformer:
            from shapely.ops import transform as shapely_transform
            geom = shapely_transform(transformer.transform, geom)

        # Build properties
        properties = {}
        for field in table.schema:
            if field.name == "geometry":
                continue

            value = table[field.name][i].as_py()
            properties[field.name] = value

        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": properties,
        })

    # Write GeoJSON
    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    with open(geojson_path, "w") as f:
        json.dump(geojson, f)

    size_bytes = geojson_path.stat().st_size

    logger.info(f"GeoJSON written: {geojson_path} ({size_bytes} bytes)")

    return {
        "num_features": num_features,
        "size_bytes": size_bytes,
    }


def _filter_by_bbox(table: pa.Table, bbox_geom) -> pa.Table:
    """Filter table by bounding box."""
    from shapely import wkb

    # Find features that intersect bbox
    mask = []

    for i in range(len(table)):
        geom_wkb = table["geometry"][i].as_py()
        geom = wkb.loads(geom_wkb)

        if geom.intersects(bbox_geom):
            mask.append(i)

    # Filter table
    return table.take(mask)
