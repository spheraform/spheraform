"""Download and export endpoints."""

import logging
import os
import tempfile
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas import DownloadRequest, DownloadResponse, JobStatusResponse
from spheraform_core.models import Dataset, DownloadJob, JobStatus, Geoserver, ProviderType
from spheraform_core.adapters import ArcGISAdapter

logger = logging.getLogger("gunicorn.error")
router = APIRouter()


@router.post("", response_model=DownloadResponse)
async def download_datasets(request: DownloadRequest, db: Session = Depends(get_db)):
    """
    Download datasets in the specified format.

    For small datasets, returns the file directly.
    For large datasets, queues a job and returns job_id.
    """
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

    # Check if any datasets require async processing
    needs_async = any(d.download_strategy in ["chunked", "distributed"] for d in datasets)

    if needs_async or request.merge:
        # Create download job
        job = DownloadJob(
            dataset_id=datasets[0].id,  # For now, single dataset
            status=JobStatus.PENDING,
            strategy="simple",  # Will be determined by downloader
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

        return DownloadResponse(
            job_id=job.id,
            status="queued",
        )

    # For small datasets, return immediate download URL
    # TODO: Implement direct download
    return DownloadResponse(
        download_url=f"/api/v1/download/{datasets[0].id}/file",
        status="ready",
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: UUID, db: Session = Depends(get_db)):
    """Get the status of a download job."""
    job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Calculate progress
    progress = None
    if job.total_chunks:
        progress = (job.chunks_completed / job.total_chunks) * 100

    return JobStatusResponse(
        id=job.id,
        status=job.status.value,
        progress=progress,
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

    # If force_refresh or not cached, trigger fetch job
    if force_refresh or not dataset.is_cached:
        # Create download job
        job = DownloadJob(
            dataset_id=dataset.id,
            status=JobStatus.PENDING,
            strategy=dataset.download_strategy.value,
            chunks_completed=0,
            retry_count=0,
            params={
                "dataset_ids": [str(dataset.id)],
                "format": "geojson",
            },
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # TODO: Queue job for background worker
        # For now, return job_id and let client poll
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail={
                "message": "Dataset fetch queued",
                "job_id": str(job.id),
                "poll_url": f"/api/v1/download/jobs/{job.id}",
            },
        )

    # Dataset is cached - check if we have a cache_table (PostGIS) or file
    if dataset.cache_table:
        # Export from PostGIS table to GeoJSON file
        try:
            import json
            from sqlalchemy import text

            # Create temp file
            temp_fd, temp_path = tempfile.mkstemp(suffix=".geojson", prefix=f"dataset_{dataset_id}_")
            os.close(temp_fd)

            # Query PostGIS table and export as GeoJSON
            # Use ST_AsGeoJSON to convert geometry to GeoJSON
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

            result = db.execute(query).scalar()

            # Write to file
            with open(temp_path, 'w') as f:
                json.dump(result, f)

            # Return the file
            filename = f"{dataset.name.replace(' ', '_')}_{dataset_id}.geojson"

            return FileResponse(
                path=temp_path,
                media_type="application/geo+json",
                filename=filename,
                background=None,
            )

        except Exception as e:
            logger.error(f"Failed to export from PostGIS: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to export cached data: {str(e)}",
            )
    else:
        # No cache available
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dataset marked as cached but no cache_table found",
        )
