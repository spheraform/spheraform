"""Download and export endpoints."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas import DownloadRequest, DownloadResponse, JobStatusResponse
from spheraform_core.models import Dataset, DownloadJob, JobStatus

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
