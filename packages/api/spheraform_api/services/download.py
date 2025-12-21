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
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "hybrid")  # Options: postgis, object_storage, hybrid
USE_OBJECT_STORAGE_FOR_LARGE_DATASETS = os.getenv("USE_OBJECT_STORAGE_FOR_LARGE_DATASETS", "true").lower() == "true"
MIN_FEATURES_FOR_OBJECT_STORAGE = int(os.getenv("MIN_FEATURES_FOR_OBJECT_STORAGE", "10000"))


class DownloadService:
    """Service for downloading and caching datasets."""

    def __init__(self, db: Session):
        self.db = db

    def _should_use_object_storage(self, dataset: Dataset, feature_count: Optional[int] = None) -> bool:
        """
        Determine if dataset should use object storage (S3/MinIO/GCS/Azure).

        Args:
            dataset: Dataset object
            feature_count: Optional feature count (if known before download)

        Returns:
            True if should use object storage, False for PostGIS
        """
        # Check global storage backend setting (overrides everything)
        if STORAGE_BACKEND == "object_storage":
            logger.info(f"STORAGE_BACKEND=object_storage, using object storage for {dataset.name}")
            return True
        elif STORAGE_BACKEND == "postgis":
            logger.info(f"STORAGE_BACKEND=postgis, using PostGIS for {dataset.name}")
            return False

        # Hybrid mode - decide based on dataset characteristics
        if not USE_OBJECT_STORAGE_FOR_LARGE_DATASETS:
            return False

        # If dataset explicitly configured for object storage (from previous downloads)
        if dataset.use_s3_storage:
            logger.info(f"Dataset {dataset.name} already configured for object storage")
            return True

        # Check feature count threshold
        count = feature_count or dataset.feature_count
        if count and count >= MIN_FEATURES_FOR_OBJECT_STORAGE:
            logger.info(f"Dataset has {count:,} features (>= {MIN_FEATURES_FOR_OBJECT_STORAGE:,}), using object storage")
            return True

        # Check download strategy - use object storage for chunked/distributed
        if dataset.download_strategy in [DownloadStrategy.CHUNKED, DownloadStrategy.DISTRIBUTED]:
            logger.info(f"Dataset uses {dataset.download_strategy.value} strategy, using object storage")
            return True

        logger.info(f"Using PostGIS for {dataset.name} (< {MIN_FEATURES_FOR_OBJECT_STORAGE} features)")
        return False

    async def download_and_cache(
        self,
        dataset_id: UUID,
        geometry: Optional[dict] = None,
        format: str = "geojson",
        job_id: Optional[UUID] = None,
        progress_callback: Optional[callable] = None,
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
                    # Use maxRecordCount from dataset metadata (extracted during discovery)
                    max_records = dataset.max_record_count
                    if max_records:
                        logger.info(f"Using maxRecordCount {max_records} from dataset metadata")

                    # Download based on strategy
                    # Note: Using download_paged for all strategies since it accepts full layer_url
                    # download_simple assumes base_url + "/FeatureServer/{external_id}" which may not match all servers
                    if dataset.download_strategy == DownloadStrategy.SIMPLE:
                        logger.info(f"Using simple download (via paged) for {dataset.name}")
                        result = await adapter.download_paged(
                            layer_url=dataset.access_url,
                            output_path=temp_path,
                            max_records=max_records,
                            geometry=geometry,
                            format=format,
                            progress_callback=progress_callback,
                        )
                    elif dataset.download_strategy == DownloadStrategy.PAGED:
                        logger.info(f"Using paged download for {dataset.name}")
                        result = await adapter.download_paged(
                            layer_url=dataset.access_url,
                            output_path=temp_path,
                            max_records=max_records,
                            geometry=geometry,
                            format=format,
                            progress_callback=progress_callback,
                        )
                    else:
                        # Default to paged for compatibility
                        logger.info(f"Falling back to paged download for {dataset.name}")
                        result = await adapter.download_paged(
                            layer_url=dataset.access_url,
                            output_path=temp_path,
                            max_records=max_records,
                            geometry=geometry,
                            format=format,
                            progress_callback=progress_callback,
                        )

                    if not result.success:
                        raise Exception(f"Download failed: {result.error}")

                    logger.info(f"Downloaded {result.feature_count} features to {temp_path}")

                    # Validate feature count from download result (avoid loading entire file into memory)
                    if not result.feature_count or result.feature_count == 0:
                        raise Exception(f"Download returned 0 features - dataset may be unavailable or query unsupported by server")

                    # Determine storage backend - hybrid approach for large datasets
                    use_object_storage = self._should_use_object_storage(dataset, feature_count=result.feature_count)

                    # ALWAYS store in PostGIS for tile serving (Martin compatibility)
                    logger.info(f"Storing in PostGIS for tile serving: {dataset.name}")
                    postgis_backend = PostGISStorageBackend(self.db)
                    postgis_result = await postgis_backend.store_dataset(
                        dataset_id=dataset_id,
                        geojson_path=temp_path,
                        job_id=job_id,
                    )

                    # Update dataset with PostGIS metadata
                    dataset.is_cached = True
                    dataset.cached_at = datetime.utcnow()
                    dataset.cache_table = postgis_result["cache_table"]
                    dataset.storage_format = "hybrid" if use_object_storage else "postgis"
                    if postgis_result["feature_count"]:
                        dataset.feature_count = postgis_result["feature_count"]

                    # ALSO store in object storage for large datasets (data exports & future PMTiles)
                    if use_object_storage:
                        logger.info(f"ALSO storing in object storage for data access: {dataset.name}")
                        s3_backend = S3StorageBackend(self.db)
                        s3_result = await s3_backend.store_dataset(
                            dataset_id=dataset_id,
                            geojson_path=temp_path,
                            job_id=job_id,
                        )

                        # Add object storage metadata
                        dataset.use_s3_storage = True
                        dataset.s3_data_key = s3_result["s3_data_key"]
                        dataset.parquet_schema = s3_result.get("parquet_schema")

                        # Generate PMTiles for ALL datasets in object storage
                        logger.info(f"Generating PMTiles for {dataset.name}")

                        import tempfile
                        with tempfile.TemporaryDirectory() as pmtiles_temp_dir:
                            pmtiles_path = Path(pmtiles_temp_dir) / "tiles.pmtiles"

                            # Adaptive zoom levels based on feature count
                            max_zoom = 14 if result.feature_count < 100000 else 12

                            from spheraform_core.storage.pmtiles_gen import generate_from_geojson
                            pmtiles_metadata = generate_from_geojson(
                                geojson_path=temp_path,
                                pmtiles_path=pmtiles_path,
                                min_zoom=0,
                                max_zoom=max_zoom,
                                layer_name=str(dataset_id),
                                simplification=10,
                                buffer=64,
                            )

                            # Upload to S3
                            tiles_key = f"datasets/{dataset_id}/tiles.pmtiles"
                            await s3_backend.s3_client.upload_file(
                                pmtiles_path,
                                tiles_key,
                                metadata={
                                    "min_zoom": str(pmtiles_metadata["min_zoom"]),
                                    "max_zoom": str(pmtiles_metadata["max_zoom"]),
                                    "layer_name": pmtiles_metadata["layer_name"],
                                },
                            )

                            # Get PMTiles file size
                            pmtiles_size = pmtiles_path.stat().st_size

                            # Update dataset with PMTiles metadata
                            dataset.s3_tiles_key = tiles_key
                            dataset.pmtiles_generated = True
                            dataset.pmtiles_generated_at = datetime.utcnow()
                            dataset.pmtiles_size_bytes = pmtiles_size

                            logger.info(f"PMTiles generated: {tiles_key} ({pmtiles_size} bytes)")

                        # Total size is PostGIS + object storage + PMTiles
                        dataset.cache_size_bytes = postgis_result["size_bytes"] + s3_result["size_bytes"] + dataset.pmtiles_size_bytes

                        response = {
                            "success": True,
                            "dataset_id": str(dataset_id),
                            "storage_backend": "hybrid",
                            "cache_table": postgis_result["cache_table"],
                            "s3_data_key": s3_result["s3_data_key"],
                            "s3_tiles_key": dataset.s3_tiles_key,
                            "pmtiles_generated": dataset.pmtiles_generated,
                            "pmtiles_size_bytes": dataset.pmtiles_size_bytes,
                            "feature_count": postgis_result["feature_count"],
                            "size_bytes": dataset.cache_size_bytes,
                        }
                    else:
                        # Small dataset - PostGIS only
                        dataset.use_s3_storage = False
                        dataset.cache_size_bytes = postgis_result["size_bytes"]

                        response = {
                            "success": True,
                            "dataset_id": str(dataset_id),
                            "storage_backend": "postgis",
                            "cache_table": postgis_result["cache_table"],
                            "feature_count": postgis_result["feature_count"],
                            "size_bytes": postgis_result["size_bytes"],
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
