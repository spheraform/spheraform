"""Storage backend abstraction for geodata caching."""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from uuid import UUID
from datetime import datetime
import tempfile

from sqlalchemy.orm import Session
from sqlalchemy import text

from spheraform_core.models import DownloadJob, JobStatus

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    def __init__(self, db: Session):
        """
        Initialize storage backend.

        Args:
            db: Database session
        """
        self.db = db

    @abstractmethod
    async def store_dataset(
        self,
        dataset_id: UUID,
        geojson_path: str | Path,
        job_id: Optional[UUID] = None,
    ) -> dict:
        """
        Store dataset from GeoJSON file.

        Args:
            dataset_id: Dataset UUID
            geojson_path: Path to GeoJSON file
            job_id: Optional DownloadJob ID for progress tracking

        Returns:
            Dict with storage metadata (varies by backend)
        """
        pass

    @abstractmethod
    async def retrieve_dataset(
        self,
        dataset_id: UUID,
        bbox: Optional[tuple[float, float, float, float]] = None,
    ) -> str:
        """
        Retrieve dataset as GeoJSON.

        Args:
            dataset_id: Dataset UUID
            bbox: Optional bounding box filter (minx, miny, maxx, maxy)

        Returns:
            Path to GeoJSON file
        """
        pass


class PostGISStorageBackend(StorageBackend):
    """PostGIS storage backend (legacy)."""

    async def store_dataset(
        self,
        dataset_id: UUID,
        geojson_path: str | Path,
        job_id: Optional[UUID] = None,
    ) -> dict:
        """
        Store dataset in PostGIS table using streaming to avoid memory issues.

        Args:
            dataset_id: Dataset UUID
            geojson_path: Path to GeoJSON file
            job_id: Optional DownloadJob ID for progress tracking

        Returns:
            Dict with cache_table, feature_count, size_bytes
        """
        geojson_path = Path(geojson_path)

        # Create cache table name
        cache_table = f"cache_{dataset_id.hex}"

        # Store in PostGIS using streaming (no full file load into memory)
        feature_count = await self._store_in_postgis_streaming(
            cache_table=cache_table,
            geojson_path=geojson_path,
            job_id=job_id,
        )

        # Get file size
        size_bytes = geojson_path.stat().st_size

        return {
            "cache_table": cache_table,
            "feature_count": feature_count,
            "size_bytes": size_bytes,
        }

    async def retrieve_dataset(
        self,
        dataset_id: UUID,
        bbox: Optional[tuple[float, float, float, float]] = None,
    ) -> str:
        """
        Retrieve dataset from PostGIS as GeoJSON.

        Args:
            dataset_id: Dataset UUID
            bbox: Optional bounding box filter (minx, miny, maxx, maxy)

        Returns:
            Path to temporary GeoJSON file
        """
        from spheraform_core.models import Dataset

        # Get dataset
        dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset or not dataset.cache_table:
            raise ValueError(f"Dataset {dataset_id} not cached in PostGIS")

        cache_table = dataset.cache_table

        # Build query with optional bbox filter
        if bbox:
            minx, miny, maxx, maxy = bbox
            bbox_wkt = f"POLYGON(({minx} {miny}, {maxx} {miny}, {maxx} {maxy}, {minx} {maxy}, {minx} {miny}))"

            query = text(f"""
                SELECT jsonb_build_object(
                    'type', 'FeatureCollection',
                    'features', jsonb_agg(
                        jsonb_build_object(
                            'type', 'Feature',
                            'geometry', ST_AsGeoJSON(ST_Transform(geom, 4326))::jsonb,
                            'properties', properties
                        )
                    )
                )
                FROM {cache_table}
                WHERE ST_Intersects(
                    ST_Transform(geom, 4326),
                    ST_GeomFromText(:bbox_wkt, 4326)
                )
            """)

            result = self.db.execute(query, {"bbox_wkt": bbox_wkt}).scalar()
        else:
            query = text(f"""
                SELECT jsonb_build_object(
                    'type', 'FeatureCollection',
                    'features', jsonb_agg(
                        jsonb_build_object(
                            'type', 'Feature',
                            'geometry', ST_AsGeoJSON(ST_Transform(geom, 4326))::jsonb,
                            'properties', properties
                        )
                    )
                )
                FROM {cache_table}
            """)

            result = self.db.execute(query).scalar()

        # Write to temporary file
        temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".geojson", delete=False
        )

        if result is None:
            # Empty table
            geojson_data = {"type": "FeatureCollection", "features": []}
        else:
            geojson_data = result

        json.dump(geojson_data, temp_file)
        temp_file.close()

        return temp_file.name

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

            batch = features[i : i + batch_size]

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
                    text(insert_sql), {"geometry": geometry_json, "properties": properties_json}
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

    async def _store_in_postgis_streaming(
        self,
        cache_table: str,
        geojson_path: Path,
        job_id: Optional[UUID] = None,
    ) -> int:
        """
        Store GeoJSON data in PostGIS table using streaming parser (ijson).
        Avoids loading entire file into memory for large datasets.

        Args:
            cache_table: Name of the cache table
            geojson_path: Path to GeoJSON file
            job_id: Optional DownloadJob ID for progress updates

        Returns:
            Total feature count
        """
        import ijson

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

        logger.info(f"Streaming GeoJSON to PostGIS table {cache_table}")

        # Update job stage
        if job_id:
            job = self.db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
            if job:
                job.current_stage = "storing"
                self.db.commit()

        # Stream parse features using ijson (no full file load)
        feature_count = 0
        batch = []
        batch_size = 1000

        with open(geojson_path, "rb") as f:
            # Parse features array from GeoJSON
            features = ijson.items(f, "features.item")

            for feature in features:
                # Check if job was cancelled
                if job_id and feature_count % 1000 == 0:
                    job = self.db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
                    if job and job.status == JobStatus.CANCELLED:
                        logger.info(f"Download job {job_id} was cancelled, stopping storage")
                        self.db.execute(text(f"DROP TABLE IF EXISTS {cache_table}"))
                        self.db.commit()
                        return feature_count

                batch.append(feature)
                feature_count += 1

                # Insert batch when full
                if len(batch) >= batch_size:
                    self._insert_batch(cache_table, batch)
                    batch = []

                    # Update progress
                    if job_id:
                        job = self.db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
                        if job:
                            if not job.total_features:
                                job.total_features = feature_count  # Will be updated as we stream
                            job.features_stored = feature_count
                            self.db.commit()

                    # Log progress every 10k features
                    if feature_count % 10000 == 0:
                        logger.info(f"Streamed {feature_count:,} features to PostGIS")

            # Insert remaining features
            if batch:
                self._insert_batch(cache_table, batch)

        # Update final feature count
        if job_id:
            job = self.db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
            if job:
                job.total_features = feature_count
                job.features_stored = feature_count
                self.db.commit()

        # Create spatial index
        if job_id:
            job = self.db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
            if job:
                job.current_stage = "indexing"
                self.db.commit()

        logger.info(f"Creating spatial index on {cache_table}")
        self.db.execute(text(f"CREATE INDEX {cache_table}_geom_idx ON {cache_table} USING GIST (geom)"))
        self.db.commit()

        logger.info(f"Successfully stored {feature_count:,} features in {cache_table}")
        return feature_count

    def _insert_batch(self, cache_table: str, batch: list):
        """Insert a batch of features into PostGIS table."""
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
                text(insert_sql), {"geometry": geometry_json, "properties": properties_json}
            )


class S3StorageBackend(StorageBackend):
    """S3/MinIO storage backend (GeoParquet + PMTiles)."""

    def __init__(self, db: Session, s3_client=None):
        """
        Initialize S3 storage backend.

        Args:
            db: Database session
            s3_client: S3Client instance (optional, will create if not provided)
        """
        super().__init__(db)

        if s3_client is None:
            from .s3_client import S3Client

            self.s3_client = S3Client()
        else:
            self.s3_client = s3_client

    async def store_dataset(
        self,
        dataset_id: UUID,
        geojson_path: str | Path,
        job_id: Optional[UUID] = None,
    ) -> dict:
        """
        Store dataset in S3 as GeoParquet + PMTiles.

        Args:
            dataset_id: Dataset UUID
            geojson_path: Path to GeoJSON file
            job_id: Optional DownloadJob ID for progress tracking

        Returns:
            Dict with s3_data_key, s3_tiles_key, feature_count, size_bytes
        """
        from .geoparquet import geojson_to_geoparquet
        from .pmtiles_gen import generate_from_geojson

        geojson_path = Path(geojson_path)

        logger.info(f"Storing dataset {dataset_id} in S3")

        # Update job stage
        if job_id:
            job = self.db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
            if job:
                job.current_stage = "uploading"
                self.db.commit()

        # 1. Upload GeoJSON to landing zone
        landing_key = f"landing/{job_id or dataset_id}/data.geojson"

        logger.info(f"Uploading GeoJSON to landing zone: {landing_key}")
        await self.s3_client.upload_file(geojson_path, landing_key)

        # 2. Convert to GeoParquet and upload
        if job_id:
            job = self.db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
            if job:
                job.current_stage = "converting_parquet"
                self.db.commit()

        with tempfile.TemporaryDirectory() as temp_dir:
            parquet_path = Path(temp_dir) / "data.parquet"

            logger.info(f"Converting to GeoParquet: {parquet_path}")
            parquet_metadata = geojson_to_geoparquet(geojson_path, parquet_path)

            # Upload GeoParquet
            data_key = f"datasets/{dataset_id}/data.parquet"
            logger.info(f"Uploading GeoParquet to S3: {data_key}")
            await self.s3_client.upload_file(
                parquet_path,
                data_key,
                metadata={
                    "num_features": str(parquet_metadata["num_features"]),
                    "schema": parquet_metadata["schema"][:1000],  # Truncate for S3 metadata limits
                },
            )

            # 3. Generate PMTiles and upload
            if job_id:
                job = self.db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
                if job:
                    job.current_stage = "generating_tiles"
                    self.db.commit()

            pmtiles_path = Path(temp_dir) / "tiles.pmtiles"

            logger.info(f"Generating PMTiles: {pmtiles_path}")
            pmtiles_metadata = generate_from_geojson(
                geojson_path,
                pmtiles_path,
                layer_name=str(dataset_id),
            )

            # Upload PMTiles
            tiles_key = f"datasets/{dataset_id}/tiles.pmtiles"
            logger.info(f"Uploading PMTiles to S3: {tiles_key}")
            await self.s3_client.upload_file(
                pmtiles_path,
                tiles_key,
                metadata={
                    "min_zoom": str(pmtiles_metadata["min_zoom"]),
                    "max_zoom": str(pmtiles_metadata["max_zoom"]),
                    "layer_name": pmtiles_metadata["layer_name"],
                },
            )

        # 4. Clean up landing zone
        logger.info(f"Cleaning up landing zone: {landing_key}")
        await self.s3_client.delete_object(landing_key)

        # 5. Return metadata
        logger.info(f"Successfully stored dataset {dataset_id} in S3")

        return {
            "s3_data_key": data_key,
            "s3_tiles_key": tiles_key,
            "feature_count": parquet_metadata["num_features"],
            "size_bytes": parquet_metadata["size_bytes"] + pmtiles_metadata["size_bytes"],
            "parquet_schema": parquet_metadata["schema"],
        }

    async def retrieve_dataset(
        self,
        dataset_id: UUID,
        bbox: Optional[tuple[float, float, float, float]] = None,
    ) -> str:
        """
        Retrieve dataset from S3 as GeoJSON.

        Args:
            dataset_id: Dataset UUID
            bbox: Optional bounding box filter (minx, miny, maxx, maxy)

        Returns:
            Path to temporary GeoJSON file
        """
        from spheraform_core.models import Dataset
        from .geoparquet import geoparquet_to_geojson

        # Get dataset
        dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset or not dataset.s3_data_key:
            raise ValueError(f"Dataset {dataset_id} not cached in S3")

        logger.info(f"Retrieving dataset {dataset_id} from S3")

        # Download GeoParquet from S3
        with tempfile.TemporaryDirectory() as temp_dir:
            parquet_path = Path(temp_dir) / "data.parquet"

            logger.info(f"Downloading GeoParquet: {dataset.s3_data_key}")
            await self.s3_client.download_file(dataset.s3_data_key, parquet_path)

            # Convert to GeoJSON
            temp_geojson = tempfile.NamedTemporaryFile(
                mode="w", suffix=".geojson", delete=False
            )
            temp_geojson_path = Path(temp_geojson.name)
            temp_geojson.close()

            logger.info(f"Converting to GeoJSON: {temp_geojson_path}")
            geoparquet_to_geojson(parquet_path, temp_geojson_path, bbox=bbox)

            return str(temp_geojson_path)
