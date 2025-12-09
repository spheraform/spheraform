"""Download service for fetching and caching datasets."""

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import text

from spheraform_core.models import Dataset, Geoserver, DownloadStrategy, DownloadJob
from spheraform_core.adapters import ArcGISAdapter

logger = logging.getLogger("gunicorn.error")


class DownloadService:
    """Service for downloading and caching datasets."""

    def __init__(self, db: Session):
        self.db = db

    async def download_and_cache(
        self,
        dataset_id: UUID,
        geometry: Optional[dict] = None,
        format: str = "geojson",
        job_id: Optional[UUID] = None,
    ) -> dict:
        """
        Download dataset and cache it in PostGIS.

        Args:
            dataset_id: Dataset UUID
            geometry: Optional spatial filter
            format: Output format (geojson)

        Returns:
            dict with status, feature_count, cache_table, etc.
        """
        # Get dataset and server info
        dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        geoserver = self.db.query(Geoserver).filter(Geoserver.id == dataset.geoserver_id).first()
        if not geoserver:
            raise ValueError(f"Geoserver {dataset.geoserver_id} not found")

        logger.info(f"Downloading dataset {dataset.name} from {geoserver.name}")

        # Create cache table name
        cache_table = f"cache_{dataset_id.hex}"

        try:
            # Create adapter
            async with ArcGISAdapter(
                base_url=geoserver.base_url,
                country_hint=geoserver.country,
            ) as adapter:
                # Use temporary file for download
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    suffix='.geojson',
                    delete=False,
                    prefix=f"download_{dataset_id.hex}_"
                ) as temp_file:
                    temp_path = temp_file.name

                try:
                    # Download based on strategy
                    # Note: Using download_paged for all strategies since it accepts full layer_url
                    # download_simple assumes base_url + "/FeatureServer/{external_id}" which may not match all servers
                    if dataset.download_strategy == DownloadStrategy.SIMPLE:
                        logger.info(f"Using simple download (via paged) for {dataset.name}")
                        result = await adapter.download_paged(
                            layer_url=dataset.access_url,
                            output_path=temp_path,
                            max_records=50,  # Very small pages to handle complex geometries
                            geometry=geometry,
                            format=format,
                        )
                    elif dataset.download_strategy == DownloadStrategy.PAGED:
                        logger.info(f"Using paged download for {dataset.name}")
                        result = await adapter.download_paged(
                            layer_url=dataset.access_url,
                            output_path=temp_path,
                            geometry=geometry,
                            format=format,
                        )
                    else:
                        # Default to paged for compatibility
                        logger.info(f"Falling back to paged download for {dataset.name}")
                        result = await adapter.download_paged(
                            layer_url=dataset.access_url,
                            output_path=temp_path,
                            geometry=geometry,
                            format=format,
                        )

                    if not result.success:
                        raise Exception(f"Download failed: {result.error}")

                    logger.info(f"Downloaded {result.feature_count} features to {temp_path}")

                    # Load GeoJSON from temp file
                    with open(temp_path, 'r') as f:
                        geojson_data = json.load(f)

                    # Store in PostGIS
                    await self._store_in_postgis(
                        cache_table=cache_table,
                        geojson_data=geojson_data,
                        job_id=job_id,
                    )

                    # Update dataset metadata
                    dataset.is_cached = True
                    dataset.cached_at = datetime.utcnow()
                    dataset.cache_table = cache_table
                    dataset.cache_size_bytes = result.size_bytes
                    if result.feature_count:
                        dataset.feature_count = result.feature_count

                    self.db.commit()

                    logger.info(f"Successfully cached {dataset.name} in table {cache_table}")

                    return {
                        "success": True,
                        "dataset_id": str(dataset_id),
                        "cache_table": cache_table,
                        "feature_count": result.feature_count,
                        "size_bytes": result.size_bytes,
                    }

                finally:
                    # Clean up temp file
                    Path(temp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.exception(f"Error downloading dataset {dataset_id}: {e}")
            raise

    async def _store_in_postgis(
        self,
        cache_table: str,
        geojson_data: dict,
        job_id: Optional[UUID] = None,
    ) -> None:
        """
        Store GeoJSON data in PostGIS table with progress tracking.

        Args:
            cache_table: Name of the cache table
            geojson_data: GeoJSON FeatureCollection
            job_id: Optional DownloadJob ID for progress updates
        """
        # Drop table if it exists
        self.db.execute(text(f"DROP TABLE IF EXISTS {cache_table}"))

        # Create table
        create_table_sql = f"""
        CREATE TABLE {cache_table} (
            id SERIAL PRIMARY KEY,
            geom GEOMETRY(Geometry, 4326),
            properties JSONB
        )
        """
        self.db.execute(text(create_table_sql))

        # Insert features with progress tracking
        features = geojson_data.get("features", [])
        total_features = len(features)

        logger.info(f"Storing {total_features:,} features in {cache_table}")

        # Update job stage
        if job_id:
            job = self.db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
            if job:
                job.current_stage = "storing"
                job.total_features = total_features
                self.db.commit()

        # Insert in batches for better progress feedback
        batch_size = 1000
        for i in range(0, total_features, batch_size):
            batch = features[i:i+batch_size]

            for feature in batch:
                geometry_json = json.dumps(feature.get("geometry"))
                properties_json = json.dumps(feature.get("properties", {}))

                insert_sql = f"""
                INSERT INTO {cache_table} (geom, properties)
                VALUES (
                    ST_GeomFromGeoJSON(:geometry),
                    CAST(:properties AS jsonb)
                )
                """
                self.db.execute(
                    text(insert_sql),
                    {"geometry": geometry_json, "properties": properties_json}
                )

            # Update progress after each batch
            if job_id:
                job = self.db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
                if job:
                    job.features_stored = min(i + batch_size, total_features)
                    self.db.commit()

            # Log milestone progress
            if (i + batch_size) % 10000 == 0 or (i + batch_size) >= total_features:
                progress_pct = ((i + batch_size) / total_features) * 100
                logger.info(
                    f"Storage progress: {progress_pct:.1f}% "
                    f"({min(i + batch_size, total_features):,}/{total_features:,} features)"
                )

        # Create spatial index
        if job_id:
            job = self.db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
            if job:
                job.current_stage = "indexing"
                self.db.commit()

        logger.info(f"Creating spatial index on {cache_table}")
        self.db.execute(text(f"CREATE INDEX {cache_table}_geom_idx ON {cache_table} USING GIST (geom)"))

        self.db.commit()
        logger.info(f"Successfully stored {total_features:,} features in {cache_table}")

    def get_cached_geojson(self, dataset: Dataset) -> dict:
        """
        Retrieve cached GeoJSON from PostGIS.

        Args:
            dataset: Dataset object with cache_table set

        Returns:
            GeoJSON FeatureCollection dict
        """
        if not dataset.cache_table:
            raise ValueError(f"Dataset {dataset.id} has no cache table")

        logger.info(f"Retrieving cached data from {dataset.cache_table}")

        # Query PostGIS table and export as GeoJSON
        query = text(f"""
            SELECT jsonb_build_object(
                'type', 'FeatureCollection',
                'features', jsonb_agg(
                    jsonb_build_object(
                        'type', 'Feature',
                        'geometry', ST_AsGeoJSON(geom)::jsonb,
                        'properties', properties
                    )
                )
            )
            FROM {dataset.cache_table}
        """)

        result = self.db.execute(query).scalar()

        if result is None:
            # Empty table
            return {
                "type": "FeatureCollection",
                "features": []
            }

        return result
