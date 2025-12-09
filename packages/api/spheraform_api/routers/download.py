"""Download and export endpoints."""

import logging
import os
import tempfile
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas import DownloadRequest, DownloadResponse, JobStatusResponse, DownloadJobProgressResponse
from spheraform_core.models import Dataset, DownloadJob, JobStatus, Geoserver, ProviderType, DownloadStrategy
from spheraform_core.adapters import ArcGISAdapter

logger = logging.getLogger("gunicorn.error")
router = APIRouter()


@router.post("", response_model=DownloadResponse)
async def download_datasets(request: DownloadRequest, db: Session = Depends(get_db)):
    """
    Download datasets in the specified format.

    For small datasets, fetches synchronously and caches.
    For large datasets, queues a job and returns job_id.
    """
    from ..services.download import DownloadService

    # Validate that all datasets exist
    datasets = (
        db.query(Dataset)
        .filter(Dataset.id.in_(request.dataset_ids))
        .all()
    )

    if len(datasets) != len(request.dataset_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more datasets not found",
        )

    # For now, only support single dataset downloads
    if len(datasets) > 1 and request.merge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Merged downloads not yet implemented",
        )

    dataset = datasets[0]

    # Check if dataset is already cached
    if dataset.is_cached and not request.geometry and not request.force_refresh:
        logger.info(f"Dataset {dataset.id} already cached, returning download URL")
        return DownloadResponse(
            download_url=f"/api/v1/download/{dataset.id}/file",
            status="ready",
        )

    # Check if any datasets require async processing
    needs_async = dataset.download_strategy in [DownloadStrategy.CHUNKED, DownloadStrategy.DISTRIBUTED]

    if needs_async:
        # Create download job for background processing
        job = DownloadJob(
            dataset_id=dataset.id,
            status=JobStatus.PENDING,
            strategy=dataset.download_strategy.value,
            chunks_completed=0,
            retry_count=0,
            params={
                "dataset_ids": [str(d.id) for d in datasets],
                "format": request.format,
                "crs": request.crs,
                "merge": request.merge,
                "geometry": request.geometry,
            },
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        logger.info(f"Created download job {job.id} for dataset {dataset.id}")
        return DownloadResponse(
            job_id=job.id,
            status="queued",
        )

    # For small/medium datasets, download synchronously
    try:
        logger.info(f"Starting synchronous download for dataset {dataset.id}")
        download_service = DownloadService(db)
        result = await download_service.download_and_cache(
            dataset_id=dataset.id,
            geometry=request.geometry,
            format=request.format,
        )

        logger.info(f"Download completed: {result}")
        return DownloadResponse(
            download_url=f"/api/v1/download/{dataset.id}/file",
            status="completed",
        )
    except Exception as e:
        logger.exception(f"Error downloading dataset {dataset.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Download failed: {str(e)}",
        )


@router.get("/jobs/{job_id}", response_model=DownloadJobProgressResponse)
async def get_job_status(job_id: UUID, db: Session = Depends(get_db)):
    """Get detailed status and progress of a download job."""
    job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Calculate stage-based progress
    progress = None
    if job.current_stage == "downloading" and job.total_features:
        progress = (job.features_downloaded / job.total_features) * 70  # 70% for download
    elif job.current_stage == "storing" and job.total_features:
        base = 70.0
        store_progress = (job.features_stored / job.total_features) * 25  # 25% for storing
        progress = base + store_progress
    elif job.current_stage == "indexing":
        progress = 95.0
    elif job.status == JobStatus.COMPLETED:
        progress = 100.0
    elif job.total_chunks and job.total_chunks > 0:
        # Fallback to chunk-based progress
        progress = (job.chunks_completed / job.total_chunks) * 100

    return DownloadJobProgressResponse(
        id=job.id,
        dataset_id=job.dataset_id,
        status=job.status.value,
        progress=progress,
        current_stage=job.current_stage,
        total_features=job.total_features,
        features_downloaded=job.features_downloaded,
        features_stored=job.features_stored,
        chunks_completed=job.chunks_completed,
        total_chunks=job.total_chunks,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error=job.error,
        output_path=job.output_path,
    )


@router.get("/jobs/{job_id}/download")
async def download_job_result(job_id: UUID, db: Session = Depends(get_db)):
    """Download the result file from a completed job."""
    job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed (status: {job.status})",
        )

    # TODO: Return FileResponse with the actual file
    return {"download_url": job.output_path}


@router.get("/{dataset_id}/file")
async def download_dataset_file(
    dataset_id: UUID,
    force_refresh: bool = False,
    db: Session = Depends(get_db)
):
    """
    Download a cached dataset file.

    This endpoint serves cached data. If the dataset is not cached, returns 404.
    Use POST /api/v1/download to fetch and cache datasets first.

    Args:
        dataset_id: UUID of the dataset
        force_refresh: If True, re-fetch from source even if cached (default: False)
    """
    from ..services.download import DownloadService

    # Get dataset
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found",
        )

    # Check if dataset is cached
    if not force_refresh and not dataset.is_cached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset not cached. Use POST /api/v1/download to fetch it first.",
        )

    # If force_refresh, re-download the dataset
    if force_refresh:
        try:
            logger.info(f"Force refresh requested for dataset {dataset_id}")
            download_service = DownloadService(db)
            await download_service.download_and_cache(
                dataset_id=dataset_id,
                geometry=None,
                format="geojson",
            )
        except Exception as e:
            logger.exception(f"Error refreshing dataset {dataset_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to refresh dataset: {str(e)}",
            )

    # Dataset is cached - retrieve from PostGIS
    if not dataset.cache_table:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dataset marked as cached but no cache_table found",
        )

    try:
        import json

        # Create temp file
        temp_fd, temp_path = tempfile.mkstemp(suffix=".geojson", prefix=f"dataset_{dataset_id}_")
        os.close(temp_fd)

        # Get GeoJSON from service
        download_service = DownloadService(db)
        geojson_data = download_service.get_cached_geojson(dataset)

        # Write to file
        with open(temp_path, 'w') as f:
            json.dump(geojson_data, f)

        # Return the file
        filename = f"{dataset.name.replace(' ', '_')}_{dataset_id}.geojson"

        logger.info(f"Serving cached dataset {dataset_id} from {dataset.cache_table}")
        return FileResponse(
            path=temp_path,
            media_type="application/geo+json",
            filename=filename,
            background=None,
        )

    except Exception as e:
        logger.exception(f"Failed to export from PostGIS: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export cached data: {str(e)}",
        )
