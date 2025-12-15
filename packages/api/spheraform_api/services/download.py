"""Download service for fetching and caching datasets."""

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID
import os

from sqlalchemy.orm import Session
from sqlalchemy import text

from spheraform_core.models import Dataset, Geoserver, DownloadStrategy, DownloadJob, JobStatus
from spheraform_core.adapters import ArcGISAdapter
from spheraform_core.storage.backend import PostGISStorageBackend, S3StorageBackend

logger = logging.getLogger("gunicorn.error")

# Environment variable to control storage backend
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "hybrid")  # Options: postgis, s3, hybrid
USE_S3_FOR_LARGE_DATASETS = os.getenv("USE_S3_FOR_LARGE_DATASETS", "true").lower() == "true"
MIN_FEATURES_FOR_S3 = int(os.getenv("MIN_FEATURES_FOR_S3", "10000"))


class DownloadService:
    """Service for downloading and caching datasets."""

    def __init__(self, db: Session):
        self.db = db

    def _should_use_s3(self, dataset: Dataset, feature_count: Optional[int] = None) -> bool:
        """
        Determine if dataset should use S3 storage.

        Args:
            dataset: Dataset object
            feature_count: Optional feature count (if known before download)

        Returns:
            True if should use S3, False for PostGIS
        """
        # Check global storage backend setting
        if STORAGE_BACKEND == "s3":
            return True
        elif STORAGE_BACKEND == "postgis":
            return False

        # Hybrid mode - decide based on dataset characteristics
        if not USE_S3_FOR_LARGE_DATASETS:
            return False

        # If dataset explicitly configured for S3
        if dataset.use_s3_storage:
            return True

        # Check feature count threshold
        count = feature_count or dataset.feature_count
        if count and count >= MIN_FEATURES_FOR_S3:
            logger.info(f"Dataset has {count:,} features (>= {MIN_FEATURES_FOR_S3:,}), using S3 storage")
            return True

        # Check download strategy - use S3 for chunked/distributed
        if dataset.download_strategy in [DownloadStrategy.CHUNKED, DownloadStrategy.DISTRIBUTED]:
            logger.info(f"Dataset uses {dataset.download_strategy.value} strategy, using S3 storage")
            return True

        return False

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

                    # Check if GeoJSON has features
                    features = geojson_data.get("features", [])
                    if not features or len(features) == 0:
                        raise Exception(f"Download returned 0 features - dataset may be unavailable or query unsupported by server")

                    # Determine storage backend
                    use_s3 = self._should_use_s3(dataset, feature_count=result.feature_count)

                    if use_s3:
                        logger.info(f"Using S3 storage backend for {dataset.name}")
                        backend = S3StorageBackend(self.db)
                        storage_result = await backend.store_dataset(
                            dataset_id=dataset_id,
                            geojson_path=temp_path,
                            job_id=job_id,
                        )

                        # Update dataset metadata for S3
                        dataset.is_cached = True
                        dataset.cached_at = datetime.utcnow()
                        dataset.use_s3_storage = True
                        dataset.storage_format = "geoparquet"
                        dataset.s3_data_key = storage_result["s3_data_key"]
                        dataset.s3_tiles_key = storage_result["s3_tiles_key"]
                        dataset.cache_size_bytes = storage_result["size_bytes"]
                        dataset.parquet_schema = storage_result.get("parquet_schema")
                        if storage_result["feature_count"]:
                            dataset.feature_count = storage_result["feature_count"]

                        response = {
                            "success": True,
                            "dataset_id": str(dataset_id),
                            "storage_backend": "s3",
                            "s3_data_key": storage_result["s3_data_key"],
                            "s3_tiles_key": storage_result["s3_tiles_key"],
                            "feature_count": storage_result["feature_count"],
                            "size_bytes": storage_result["size_bytes"],
                        }
                    else:
                        logger.info(f"Using PostGIS storage backend for {dataset.name}")
                        backend = PostGISStorageBackend(self.db)
                        storage_result = await backend.store_dataset(
                            dataset_id=dataset_id,
                            geojson_path=temp_path,
                            job_id=job_id,
                        )

                        # Update dataset metadata for PostGIS
                        dataset.is_cached = True
                        dataset.cached_at = datetime.utcnow()
                        dataset.cache_table = storage_result["cache_table"]
                        dataset.cache_size_bytes = storage_result["size_bytes"]
                        dataset.storage_format = "postgis"
                        dataset.use_s3_storage = False
                        if storage_result["feature_count"]:
                            dataset.feature_count = storage_result["feature_count"]

                        response = {
                            "success": True,
                            "dataset_id": str(dataset_id),
                            "storage_backend": "postgis",
                            "cache_table": storage_result["cache_table"],
                            "feature_count": storage_result["feature_count"],
                            "size_bytes": storage_result["size_bytes"],
                        }

                    self.db.commit()

                    logger.info(f"Successfully cached {dataset.name}")

                    return response

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

        # Create table with SRID 3857 (Web Mercator) for Martin tile server
        create_table_sql = f"""
        CREATE TABLE {cache_table} (
            id SERIAL PRIMARY KEY,
            geom GEOMETRY(Geometry, 3857),
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
            # Check if job was cancelled
            if job_id:
                job = self.db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
                if job and job.status == JobStatus.CANCELLED:
                    logger.info(f"Download job {job_id} was cancelled, stopping storage")
                    # Clean up partial table
                    self.db.execute(text(f"DROP TABLE IF EXISTS {cache_table}"))
                    self.db.commit()
                    return

            batch = features[i:i+batch_size]

            for feature in batch:
                geometry_json = json.dumps(feature.get("geometry"))
                properties_json = json.dumps(feature.get("properties", {}))

                # Transform from 4326 (WGS84) to 3857 (Web Mercator) for Martin
                insert_sql = f"""
                INSERT INTO {cache_table} (geom, properties)
                VALUES (
                    ST_Transform(ST_GeomFromGeoJSON(:geometry), 3857),
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

    async def get_cached_geojson(self, dataset: Dataset, bbox: Optional[tuple[float, float, float, float]] = None) -> dict:
        """
        Retrieve cached GeoJSON from storage backend (PostGIS or S3).

        Args:
            dataset: Dataset object
            bbox: Optional bounding box filter (minx, miny, maxx, maxy)

        Returns:
            GeoJSON FeatureCollection dict
        """
        if not dataset.is_cached:
            raise ValueError(f"Dataset {dataset.id} is not cached")

        # Determine storage backend and retrieve
        if dataset.use_s3_storage and dataset.s3_data_key:
            logger.info(f"Retrieving cached data from S3: {dataset.s3_data_key}")
            backend = S3StorageBackend(self.db)
        elif dataset.cache_table:
            logger.info(f"Retrieving cached data from PostGIS: {dataset.cache_table}")
            backend = PostGISStorageBackend(self.db)
        else:
            raise ValueError(f"Dataset {dataset.id} has no storage metadata")

        # Get GeoJSON file path from backend
        geojson_path = await backend.retrieve_dataset(dataset.id, bbox=bbox)

        # Load GeoJSON
        try:
            with open(geojson_path, 'r') as f:
                geojson_data = json.load(f)
            return geojson_data
        finally:
            # Clean up temporary file
            Path(geojson_path).unlink(missing_ok=True)
