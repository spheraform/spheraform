"""Background worker for processing crawl jobs."""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from spheraform_core.models import (
    Geoserver,
    CrawlJob,
    Dataset,
    JobStatus,
    ProviderType,
    HealthStatus,
)
from spheraform_core.adapters import ArcGISAdapter

logger = logging.getLogger("gunicorn.error")


class CrawlWorker:
    """Worker for processing crawl jobs in the background."""

    def __init__(self, database_url: str, poll_interval: int = 5):
        """
        Initialize the crawl worker.

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
        logger.info("Crawl worker started")

        while self.running:
            try:
                with self.SessionLocal() as db:
                    self._process_pending_jobs(db)
            except Exception as e:
                logger.error(f"Error in crawl worker loop: {e}", exc_info=True)

            time.sleep(self.poll_interval)

    def stop(self):
        """Stop the worker loop."""
        self.running = False
        logger.info("Crawl worker stopped")

    def _process_pending_jobs(self, db: Session):
        """Process all pending crawl jobs."""
        pending_jobs = (
            db.query(CrawlJob).filter(CrawlJob.status == JobStatus.PENDING).all()
        )

        if pending_jobs:
            logger.info(f"Found {len(pending_jobs)} pending crawl jobs")

        for job in pending_jobs:
            try:
                # Use asyncio to run the async crawl process
                asyncio.run(self._process_job(db, job))
                db.commit()
            except Exception as e:
                logger.error(
                    f"Failed to process crawl job {job.id}: {e}", exc_info=True
                )
                db.rollback()

                # Mark job as failed
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.completed_at = datetime.utcnow()
                job.current_stage = "failed"
                db.commit()

    async def _process_job(self, db: Session, job: CrawlJob):
        """
        Process a single crawl job.

        Args:
            db: Database session
            job: CrawlJob to process
        """
        logger.info(f"Processing crawl job {job.id} for server {job.geoserver_id}")

        # Update job status to RUNNING
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        job.current_stage = "discovering"
        db.commit()

        # Get server
        server = db.query(Geoserver).filter(Geoserver.id == job.geoserver_id).first()
        if not server:
            raise ValueError(f"Server {job.geoserver_id} not found")

        datasets_new = 0
        datasets_updated = 0
        services_processed = 0

        try:
            # Create adapter with connection config and proxy support
            async with ArcGISAdapter(
                base_url=server.base_url,
                connection_config=server.connection_config,
                country_hint=server.country,
            ) as adapter:
                # First pass: count services for progress tracking
                logger.info(f"Counting services for progress tracking...")
                job.current_stage = "counting_services"
                db.commit()

                catalog = await adapter._request(server.base_url)
                total_services = len(catalog.get("services", []))
                for folder in catalog.get("folders", []):
                    folder_url = f"{server.base_url}/{folder}"
                    folder_catalog = await adapter._request(folder_url)
                    total_services += len(folder_catalog.get("services", []))

                job.total_services = total_services
                job.current_stage = "processing_datasets"
                db.commit()

                logger.info(f"Found {total_services} services to process")

                # Keep track of processed services (approximate by datasets discovered)
                last_commit_count = 0

                # Second pass: discover datasets with progress updates
                async for dataset_meta in adapter.discover_datasets():
                    # Check if job was cancelled
                    db.refresh(job)
                    if job.status == JobStatus.CANCELLED:
                        logger.info(f"Crawl job {job.id} was cancelled, stopping discovery")
                        break

                    # Update progress periodically (every 10 datasets to reduce commits)
                    datasets_discovered = datasets_new + datasets_updated

                    # Check if dataset already exists
                    existing = (
                        db.query(Dataset)
                        .filter(
                            Dataset.geoserver_id == server.id,
                            Dataset.access_url == dataset_meta.access_url,
                        )
                        .first()
                    )

                    # Convert bbox tuple to WKT POLYGON and transform to EPSG:4326
                    bbox_geometry = None
                    if dataset_meta.bbox and dataset_meta.source_srid:
                        minx, miny, maxx, maxy = dataset_meta.bbox
                        bbox_wkt = f"POLYGON(({minx} {miny},{maxx} {miny},{maxx} {maxy},{minx} {maxy},{minx} {miny}))"
                        bbox_geometry = func.ST_Transform(
                            func.ST_GeomFromText(bbox_wkt, dataset_meta.source_srid),
                            4326,
                        )

                    if existing:
                        # Update existing dataset
                        existing.name = dataset_meta.name
                        existing.description = dataset_meta.description
                        existing.access_url = dataset_meta.access_url
                        existing.feature_count = dataset_meta.feature_count
                        existing.bbox = bbox_geometry
                        existing.keywords = dataset_meta.keywords
                        existing.updated_at = datetime.utcnow()
                        existing.service_item_id = dataset_meta.service_item_id
                        existing.geometry_type = dataset_meta.geometry_type
                        existing.source_srid = dataset_meta.source_srid
                        existing.max_record_count = dataset_meta.max_record_count
                        existing.last_edit_date = dataset_meta.last_edit_date
                        existing.themes = dataset_meta.themes
                        # Store raw metadata (includes maxRecordCount, etc)
                        if dataset_meta.source_metadata:
                            import json
                            existing.source_metadata = json.dumps(dataset_meta.source_metadata) if isinstance(dataset_meta.source_metadata, dict) else dataset_meta.source_metadata
                        datasets_updated += 1
                    else:
                        # Create new dataset
                        # Store raw metadata (includes maxRecordCount, etc)
                        source_metadata_str = None
                        if dataset_meta.source_metadata:
                            import json
                            source_metadata_str = json.dumps(dataset_meta.source_metadata) if isinstance(dataset_meta.source_metadata, dict) else dataset_meta.source_metadata

                        new_dataset = Dataset(
                            geoserver_id=server.id,
                            external_id=dataset_meta.external_id,
                            name=dataset_meta.name,
                            description=dataset_meta.description,
                            access_url=dataset_meta.access_url,
                            feature_count=dataset_meta.feature_count,
                            bbox=bbox_geometry,
                            keywords=dataset_meta.keywords,
                            is_active=True,
                            service_item_id=dataset_meta.service_item_id,
                            geometry_type=dataset_meta.geometry_type,
                            source_srid=dataset_meta.source_srid,
                            max_record_count=dataset_meta.max_record_count,
                            last_edit_date=dataset_meta.last_edit_date,
                            themes=dataset_meta.themes,
                            source_metadata=source_metadata_str,
                        )
                        db.add(new_dataset)
                        datasets_new += 1

                    # Commit progress periodically (every 10 datasets)
                    if (datasets_new + datasets_updated) % 10 == 0:
                        # Estimate services processed based on datasets (rough approximation)
                        # Assume average of 5 datasets per service
                        services_processed = min(
                            (datasets_new + datasets_updated) // 5, total_services
                        )

                        job.datasets_discovered = datasets_new + datasets_updated
                        job.datasets_new = datasets_new
                        job.datasets_updated = datasets_updated
                        job.services_processed = services_processed
                        db.commit()

                        if (
                            datasets_new + datasets_updated
                        ) % 50 == 0:  # Log milestone every 50 datasets
                            logger.info(
                                f"Crawl progress: {datasets_new + datasets_updated} datasets discovered "
                                f"({datasets_new} new, {datasets_updated} updated)"
                            )

                # Final update
                services_processed = total_services  # Mark as complete
                job.datasets_discovered = datasets_new + datasets_updated
                job.datasets_new = datasets_new
                job.datasets_updated = datasets_updated
                job.services_processed = services_processed

                # Update server metadata
                job.current_stage = "finalizing"
                db.commit()

                server.last_crawl = datetime.utcnow()
                server.dataset_count = (
                    db.query(Dataset).filter(Dataset.geoserver_id == server.id).count()
                )
                server.active_dataset_count = (
                    db.query(Dataset)
                    .filter(
                        Dataset.geoserver_id == server.id, Dataset.is_active == True
                    )
                    .count()
                )
                server.health_status = HealthStatus.HEALTHY

                # Mark job as completed
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                job.current_stage = "complete"
                db.commit()

                duration = (job.completed_at - job.started_at).total_seconds()
                logger.info(
                    f"Crawl job {job.id} completed: "
                    f"discovered {job.datasets_discovered} datasets "
                    f"({job.datasets_new} new, {job.datasets_updated} updated) "
                    f"from {job.services_processed} services in {duration:.1f}s"
                )

        except Exception as e:
            server.health_status = HealthStatus.OFFLINE
            db.commit()
            raise


def start_crawl_worker_thread(database_url: str):
    """
    Start the crawl worker in a background thread.

    Args:
        database_url: Database connection URL
    """
    import threading

    worker = CrawlWorker(database_url)
    thread = threading.Thread(target=worker.start, daemon=True)
    thread.start()

    logger.info("Crawl worker thread started")
    return worker, thread
