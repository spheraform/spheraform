"""Crawl task definitions for Celery distributed processing."""

import logging
from datetime import datetime
from uuid import UUID

from celery import group
from ..celery_app import celery_app
from ..celery_utils import get_db_session
from spheraform_core.models import CrawlJob, Geoserver, Dataset, JobStatus, HealthStatus
from spheraform_core.adapters import ArcGISAdapter

logger = logging.getLogger("gunicorn.error")


@celery_app.task(bind=True, name="crawl.process_server")
def process_crawl_job(self, crawl_job_id: str):
    """
    Main entry point for crawl job.
    Discovers services and spawns parallel processing.

    Args:
        crawl_job_id: UUID of the CrawlJob to process

    Returns:
        Task result
    """
    with get_db_session() as db:
        job = db.query(CrawlJob).filter(CrawlJob.id == crawl_job_id).first()
        if not job:
            raise ValueError(f"Crawl job {crawl_job_id} not found")

        server = db.query(Geoserver).filter(Geoserver.id == job.geoserver_id).first()
        if not server:
            raise ValueError(f"Server {job.geoserver_id} not found")

        # Update status
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        job.current_stage = "discovering_services"
        db.commit()

        logger.info(f"Starting crawl job {crawl_job_id} for server {server.name}")

        try:
            # Discover all services (lightweight - just URLs)
            services_task = discover_services.delay(server.base_url, str(server.id))
            services = services_task.get()  # Wait for discovery to complete

            job.total_services = len(services)
            job.current_stage = "processing_services"
            db.commit()

            logger.info(f"Found {len(services)} services on {server.name}")

            # Process services in parallel (groups of 10)
            service_groups = [services[i:i+10] for i in range(0, len(services), 10)]

            for group_services in service_groups:
                tasks = group(
                    process_service.s(crawl_job_id, svc_url)
                    for svc_url in group_services
                )
                tasks.apply_async()  # Fire and forget

            logger.info(f"Dispatched {len(services)} services for parallel processing")

        except Exception as e:
            logger.exception(f"Crawl job {crawl_job_id} failed during service discovery: {e}")
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow()
            job.current_stage = "failed"
            job.error = str(e)
            db.commit()
            raise


@celery_app.task(name="crawl.discover_services")
async def discover_services(base_url: str, server_id: str) -> list[str]:
    """
    Discover all service URLs from ArcGIS server.

    Args:
        base_url: Base URL of the geoserver
        server_id: UUID of the Geoserver

    Returns:
        List of service URLs for parallel processing
    """
    logger.info(f"Discovering services at {base_url}")

    with get_db_session() as db:
        server = db.query(Geoserver).filter(Geoserver.id == server_id).first()

        async with ArcGISAdapter(
            base_url=base_url,
            connection_config=server.connection_config if server else None,
            country_hint=server.country if server else None,
        ) as adapter:
            try:
                catalog = await adapter._request(base_url)

                services = []
                # Root level services
                for svc in catalog.get("services", []):
                    services.append(f"{base_url}/{svc['name']}/{svc['type']}")

                # Folder services
                for folder in catalog.get("folders", []):
                    folder_url = f"{base_url}/{folder}"
                    folder_catalog = await adapter._request(folder_url)
                    for svc in folder_catalog.get("services", []):
                        services.append(f"{folder_url}/{svc['name']}/{svc['type']}")

                logger.info(f"Discovered {len(services)} services at {base_url}")
                return services

            except Exception as e:
                logger.exception(f"Failed to discover services at {base_url}: {e}")
                raise


@celery_app.task(name="crawl.process_service", bind=True, max_retries=3)
async def process_service(self, crawl_job_id: str, service_url: str):
    """
    Process single service: discover layers and store datasets.
    Runs in parallel across multiple workers.

    Args:
        crawl_job_id: UUID of the CrawlJob
        service_url: URL of the service to process

    Returns:
        Number of datasets discovered
    """
    logger.info(f"Processing service {service_url} for job {crawl_job_id}")

    with get_db_session() as db:
        job = db.query(CrawlJob).filter(CrawlJob.id == crawl_job_id).first()
        if not job:
            raise ValueError(f"Crawl job {crawl_job_id} not found")

        # Check if job was cancelled
        if job.status == JobStatus.CANCELLED:
            logger.info(f"Crawl job {crawl_job_id} was cancelled, skipping service {service_url}")
            return 0

        server = db.query(Geoserver).filter(Geoserver.id == job.geoserver_id).first()

        datasets_found = 0

        try:
            async with ArcGISAdapter(
                base_url=service_url,
                connection_config=server.connection_config,
                country_hint=server.country,
            ) as adapter:
                # Discover layers in this service
                async for dataset_meta in adapter.discover_datasets():
                    # Upsert dataset to database
                    from sqlalchemy import func

                    # Check if dataset exists
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

                        if dataset_meta.source_metadata:
                            import json
                            existing.source_metadata = json.dumps(dataset_meta.source_metadata) if isinstance(dataset_meta.source_metadata, dict) else dataset_meta.source_metadata
                    else:
                        # Create new dataset
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

                    datasets_found += 1

                    # Commit every 10 datasets to avoid long-running transactions
                    if datasets_found % 10 == 0:
                        db.commit()

                # Final commit
                db.commit()

                # Update job progress
                job.services_processed += 1
                job.datasets_discovered += datasets_found
                db.commit()

                logger.info(f"Processed service {service_url}: found {datasets_found} datasets")
                return datasets_found

        except Exception as e:
            logger.exception(f"Failed to process service {service_url}: {e}")
            # Don't fail the entire job for one service
            db.rollback()
            return 0


@celery_app.task(name="crawl.finalize_job")
def finalize_crawl_job(crawl_job_id: str):
    """
    Finalize crawl job after all services processed.

    Args:
        crawl_job_id: UUID of the CrawlJob

    Returns:
        Job summary dict
    """
    with get_db_session() as db:
        job = db.query(CrawlJob).filter(CrawlJob.id == crawl_job_id).first()
        if not job:
            raise ValueError(f"Crawl job {crawl_job_id} not found")

        server = db.query(Geoserver).filter(Geoserver.id == job.geoserver_id).first()

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
            f"Crawl job {crawl_job_id} completed: "
            f"discovered {job.datasets_discovered} datasets "
            f"from {job.services_processed} services in {duration:.1f}s"
        )

        return {
            "job_id": str(job.id),
            "datasets_discovered": job.datasets_discovered,
            "services_processed": job.services_processed,
            "duration_seconds": duration,
        }
