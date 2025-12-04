"""Download and export endpoints."""

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
    parallel: bool = True,
    workers: int = 4,
    db: Session = Depends(get_db)
):
    """
    Download a dataset file directly.

    For small datasets (<5000 features), uses simple or paged download.
    For large datasets, uses parallel OID-based download.

    Args:
        dataset_id: UUID of the dataset
        parallel: Enable parallel download (default: True)
        workers: Number of parallel workers (default: 4)
    """
    # Get dataset
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found",
        )

    # Get geoserver
    geoserver = db.query(Geoserver).filter(Geoserver.id == dataset.geoserver_id).first()
    if not geoserver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Geoserver not found for dataset",
        )

    # Only ArcGIS is currently supported
    if geoserver.provider_type != ProviderType.ARCGIS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Download not yet implemented for {geoserver.provider_type}",
        )

    try:
        # Create temp file for output
        temp_fd, temp_path = tempfile.mkstemp(suffix=".geojson", prefix=f"dataset_{dataset_id}_")
        os.close(temp_fd)  # Close the file descriptor, adapter will write to it

        # Create adapter
        async with ArcGISAdapter(
            base_url=geoserver.base_url,
            connection_config=geoserver.connection_config,
            country_hint=geoserver.country,
        ) as adapter:
            # Get feature count for logging
            feature_count = dataset.feature_count or 0

            if feature_count == 0:
                # Try to get count from server
                query_url = f"{dataset.access_url}/query"
                count_result = await adapter._request(query_url, {
                    "where": "1=1",
                    "returnCountOnly": "true",
                    "f": "json"
                })
                feature_count = count_result.get("count", 0)

            # Choose download method - check parallel parameter FIRST
            if parallel and feature_count >= 5000:
                # Use parallel download for large datasets when parallel is enabled
                print(f"Using parallel download for {feature_count} features with {workers} workers")
                result = await adapter.download_parallel(
                    layer_url=dataset.access_url,
                    output_path=temp_path,
                    num_workers=workers,
                )
            else:
                # Use paged download for all other cases:
                # - When parallel is explicitly disabled (parallel=false)
                # - When dataset is small (< 5000 features)
                # - When feature count is unknown
                reason = "parallel disabled" if not parallel else f"small dataset ({feature_count} features)"
                print(f"Using paged download: {reason}")
                result = await adapter.download_paged(
                    layer_url=dataset.access_url,
                    output_path=temp_path,
                    max_records=1000,
                )

            if not result.success:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Download failed: {result.error}",
                )

            # Return the file
            filename = f"{dataset.name.replace(' ', '_')}_{dataset_id}.geojson"

            return FileResponse(
                path=temp_path,
                media_type="application/geo+json",
                filename=filename,
                background=None,  # File will be deleted by cleanup
            )

    except HTTPException:
        raise
    except Exception as e:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Download failed: {str(e)}",
        )
