"""Background worker for processing download jobs."""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from spheraform_core.models import Dataset, DownloadJob, Geoserver, JobStatus
from spheraform_core.adapters import ArcGISAdapter

logger = logging.getLogger("gunicorn.error")


class DownloadWorker:
    """Worker for processing download jobs in the background."""

    def __init__(self, database_url: str, poll_interval: int = 5):
        """
        Initialize the download worker.

        Args:
            database_url: Database connection URL
            poll_interval: Seconds to wait between polling for new jobs
        """
        self.database_url = database_url
        self.poll_interval = poll_interval
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.running = False

    def start(self):
        """Start the worker loop."""
        self.running = True
        logger.info("Download worker started")

        while self.running:
            try:
                with self.SessionLocal() as db:
                    self._process_pending_jobs(db)
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)

            time.sleep(self.poll_interval)

    def stop(self):
        """Stop the worker loop."""
        self.running = False
        logger.info("Download worker stopped")

    def _process_pending_jobs(self, db: Session):
        """Process all pending download jobs."""
        pending_jobs = (
            db.query(DownloadJob)
            .filter(DownloadJob.status == JobStatus.PENDING)
            .all()
        )

        if pending_jobs:
            logger.info(f"Found {len(pending_jobs)} pending jobs")

        for job in pending_jobs:
            try:
                self._process_job(db, job)
                db.commit()
            except Exception as e:
                logger.error(f"Failed to process job {job.id}: {e}", exc_info=True)
                db.rollback()

                # Mark job as failed
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.completed_at = datetime.utcnow()
                db.commit()

    def _process_job(self, db: Session, job: DownloadJob):
        """
        Process a single download job.

        Args:
            db: Database session
            job: DownloadJob to process
        """
        logger.info(f"Processing job {job.id} for dataset {job.dataset_id}")

        # Update job status to RUNNING
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.commit()

        # Get dataset
        dataset = db.query(Dataset).filter(Dataset.id == job.dataset_id).first()
        if not dataset:
            raise ValueError(f"Dataset {job.dataset_id} not found")

        # Get geoserver
        geoserver = db.query(Geoserver).filter(Geoserver.id == dataset.geoserver_id).first()
        if not geoserver:
            raise ValueError(f"Geoserver {dataset.geoserver_id} not found")

        # Create adapter using the dataset's access_url (full layer endpoint)
        adapter = ArcGISAdapter(
            base_url=dataset.access_url,
        )

        # Download data
        logger.info(f"Downloading data for dataset {dataset.id}: {dataset.name}")
        geojson = adapter.download_dataset()

        if not geojson or "features" not in geojson:
            raise ValueError("Invalid GeoJSON returned from adapter")

        feature_count = len(geojson["features"])
        logger.info(f"Downloaded {feature_count} features for dataset {dataset.id}")

        # Create PostGIS table name (sanitize dataset id)
        table_name = f"cache_{str(dataset.id).replace('-', '_')}"

        # Create PostGIS table and load data
        self._create_and_load_postgis_table(db, table_name, geojson)

        # Calculate size
        geojson_str = json.dumps(geojson)
        size_bytes = len(geojson_str.encode('utf-8'))

        # Update dataset cache fields
        dataset.is_cached = True
        dataset.cached_at = datetime.utcnow()
        dataset.cache_table = table_name
        dataset.cache_size_bytes = size_bytes

        # Update job status
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.utcnow()
        job.output_path = table_name

        logger.info(f"Job {job.id} completed successfully. Data cached in table {table_name}")

    def _create_and_load_postgis_table(self, db: Session, table_name: str, geojson: dict):
        """
        Create a PostGIS table and load GeoJSON features into it.

        Args:
            db: Database session
            table_name: Name of the table to create
            geojson: GeoJSON FeatureCollection to load
        """
        logger.info(f"Creating PostGIS table {table_name}")

        # Drop table if exists
        db.execute(text(f"DROP TABLE IF EXISTS {table_name}"))

        # Create table with geometry column
        db.execute(text(f"""
            CREATE TABLE {table_name} (
                id SERIAL PRIMARY KEY,
                geom GEOMETRY,
                properties JSONB
            )
        """))

        # Create spatial index
        db.execute(text(f"""
            CREATE INDEX {table_name}_geom_idx ON {table_name} USING GIST (geom)
        """))

        db.commit()

        # Insert features
        features = geojson.get("features", [])
        logger.info(f"Loading {len(features)} features into {table_name}")

        for i, feature in enumerate(features):
            try:
                geometry = feature.get("geometry")
                properties = feature.get("properties", {})

                if not geometry:
                    logger.warning(f"Feature {i} has no geometry, skipping")
                    continue

                # Convert geometry to WKT using ST_GeomFromGeoJSON
                geometry_json = json.dumps(geometry)

                db.execute(text(f"""
                    INSERT INTO {table_name} (geom, properties)
                    VALUES (ST_GeomFromGeoJSON(:geom_json), :properties::jsonb)
                """), {
                    "geom_json": geometry_json,
                    "properties": json.dumps(properties)
                })

            except Exception as e:
                logger.error(f"Failed to insert feature {i}: {e}")
                # Continue with next feature

        db.commit()
        logger.info(f"Successfully loaded {len(features)} features into {table_name}")


def start_worker_thread(database_url: str):
    """
    Start the download worker in a background thread.

    Args:
        database_url: Database connection URL
    """
    import threading

    worker = DownloadWorker(database_url)
    thread = threading.Thread(target=worker.start, daemon=True)
    thread.start()

    logger.info("Download worker thread started")
    return worker, thread
