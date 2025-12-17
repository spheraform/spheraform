"""Download task definitions for Celery distributed processing."""

import logging
from datetime import datetime
from uuid import UUID

from celery import group, chord
from ..celery_app import celery_app
from ..celery_utils import get_db_session
from spheraform_core.models import DownloadJob, Dataset, JobStatus, DownloadStrategy
from spheraform_core.adapters import ArcGISAdapter

logger = logging.getLogger("gunicorn.error")


@celery_app.task(bind=True, name="download.process_job")
def process_download_job(self, job_id: str):
    """
    Main entry point for download job.
    Determines strategy and spawns appropriate subtasks.

    Args:
        job_id: UUID of the DownloadJob to process

    Returns:
        Task result or spawns subtasks
    """
    with get_db_session() as db:
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if not job:
            raise ValueError(f"Download job {job_id} not found")

        dataset = db.query(Dataset).filter(Dataset.id == job.dataset_id).first()
        if not dataset:
            raise ValueError(f"Dataset {job.dataset_id} not found")

        # Update status
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        job.current_stage = "routing"
        db.commit()

        logger.info(f"Processing download job {job_id} with strategy {dataset.download_strategy}")

        # Strategy selection
        if dataset.download_strategy == DownloadStrategy.SIMPLE:
            return download_simple.delay(job_id)
        elif dataset.download_strategy == DownloadStrategy.PAGED:
            return download_paged.delay(job_id)
        elif dataset.download_strategy == DownloadStrategy.CHUNKED:
            # Parallel chunks
            return download_chunked.delay(job_id)
        else:
            # Default to paged download
            logger.warning(f"Unknown strategy {dataset.download_strategy}, falling back to paged")
            return download_paged.delay(job_id)


@celery_app.task(name="download.simple")
def download_simple(job_id: str):
    """
    Single-request download for small datasets.

    Note: Celery tasks must be synchronous. Use asyncio.run() for async code.

    Args:
        job_id: UUID of the DownloadJob

    Returns:
        Download result dict
    """
    import asyncio
    from ..services.download import DownloadService

    with get_db_session() as db:
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if not job:
            raise ValueError(f"Download job {job_id} not found")

        dataset = db.query(Dataset).filter(Dataset.id == job.dataset_id).first()

        try:
            logger.info(f"Starting simple download for dataset {dataset.name}")
            download_service = DownloadService(db)

            job.current_stage = "downloading"
            db.commit()

            # Run async code in event loop
            result = asyncio.run(download_service.download_and_cache(
                dataset_id=dataset.id,
                geometry=job.params.get("geometry"),
                format=job.params.get("format", "geojson"),
                job_id=UUID(job_id),
            ))

            # Mark job as completed
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.current_stage = "complete"
            job.output_path = f"/api/v1/download/{dataset.id}/file"
            db.commit()

            logger.info(f"Simple download completed for job {job_id}")
            return result

        except Exception as e:
            logger.exception(f"Simple download failed for job {job_id}: {e}")
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow()
            job.current_stage = "failed"
            job.error = str(e)
            db.commit()
            raise


@celery_app.task(name="download.paged")
def download_paged(job_id: str):
    """
    Sequential paged download for medium datasets.
    Uses async pagination within single task.

    Note: Celery tasks must be synchronous. Use asyncio.run() for async code.

    Args:
        job_id: UUID of the DownloadJob

    Returns:
        Download result dict
    """
    import asyncio
    from ..services.download import DownloadService

    with get_db_session() as db:
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if not job:
            raise ValueError(f"Download job {job_id} not found")

        dataset = db.query(Dataset).filter(Dataset.id == job.dataset_id).first()

        try:
            logger.info(f"Starting paged download for dataset {dataset.name}")
            download_service = DownloadService(db)

            job.current_stage = "downloading"
            db.commit()

            # Run async code in event loop
            result = asyncio.run(download_service.download_and_cache(
                dataset_id=dataset.id,
                geometry=job.params.get("geometry"),
                format=job.params.get("format", "geojson"),
                job_id=UUID(job_id),
            ))

            # Mark job as completed
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.current_stage = "complete"
            job.output_path = f"/api/v1/download/{dataset.id}/file"
            db.commit()

            logger.info(f"Paged download completed for job {job_id}")
            return result

        except Exception as e:
            logger.exception(f"Paged download failed for job {job_id}: {e}")
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow()
            job.current_stage = "failed"
            job.error = str(e)
            db.commit()
            raise


@celery_app.task(name="download.chunked")
def download_chunked(job_id: str):
    """
    Parallel chunked download for large datasets.
    Spawns multiple fetch_chunk subtasks.

    Args:
        job_id: UUID of the DownloadJob

    Returns:
        Chord workflow result
    """
    # TODO: Implement parallel chunked download
    # This will:
    # 1. Calculate OID ranges
    # 2. Create parallel group of fetch_chunk tasks
    # 3. Use chord to merge results after all chunks complete
    logger.info(f"Chunked download not yet implemented for job {job_id}, falling back to paged")
    return download_paged.delay(job_id)


@celery_app.task(name="download.fetch_chunk", bind=True, max_retries=3)
async def fetch_chunk(self, job_id: str, chunk_id: int, min_oid: int, max_oid: int):
    """
    Fetch single chunk of dataset using OID range.
    Parallel execution across multiple workers.

    Args:
        job_id: UUID of the DownloadJob
        chunk_id: Chunk identifier
        min_oid: Minimum ObjectID
        max_oid: Maximum ObjectID

    Returns:
        Chunk result dict with features
    """
    # TODO: Implement OID-based chunk fetching
    # This will fetch features where OBJECTID >= min_oid AND OBJECTID < max_oid
    # Store chunk in landing zone: s3://bucket/landing/{job_id}/chunk_{chunk_id}.geojson
    pass


@celery_app.task(name="download.merge_chunks")
def merge_chunks(chunk_results: list, job_id: str):
    """
    Merge all chunks into final dataset.
    Stores in PostGIS + object storage (hybrid).

    Args:
        chunk_results: List of chunk result dicts from fetch_chunk tasks
        job_id: UUID of the DownloadJob

    Returns:
        Merge result dict
    """
    # TODO: Implement chunk merging
    # This will:
    # 1. Concatenate GeoJSON chunks
    # 2. Store in PostGIS for tile serving
    # 3. Store in S3 as GeoParquet
    # 4. Generate PMTiles
    pass
