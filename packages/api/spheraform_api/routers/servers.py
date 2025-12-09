"""Server management endpoints."""
import logging
from typing import List
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..dependencies import get_db
from ..schemas import ServerCreate, ServerUpdate, ServerResponse, CrawlJobResponse
from spheraform_core.models import Geoserver, HealthStatus, Dataset, ProviderType, CrawlJob, JobStatus
from spheraform_core.adapters import ArcGISAdapter

router = APIRouter()
logger = logging.getLogger("gunicorn.error")


@router.post("", response_model=ServerResponse, status_code=status.HTTP_201_CREATED)
async def create_server(server: ServerCreate, db: Session = Depends(get_db)):
    """
    Register a new geoserver.

    This will create the server record and can optionally trigger a crawl.
    """
    # Create new server
    db_server = Geoserver(
        name=server.name,
        base_url=server.base_url,
        provider_type=server.provider_type,
        auth_config=server.auth_config,
        connection_config=server.connection_config,
        probe_frequency_hours=server.probe_frequency_hours,
        description=server.description,
        contact_email=server.contact_email,
        organization=server.organization,
        country=server.country,
        health_status=HealthStatus.UNKNOWN,
        dataset_count=0,
        active_dataset_count=0,
    )

    db.add(db_server)
    db.commit()
    db.refresh(db_server)

    return db_server


@router.get("", response_model=List[ServerResponse])
async def list_servers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List all registered geoservers."""
    servers = db.query(Geoserver).offset(skip).limit(limit).all()
    return servers


@router.get("/{server_id}", response_model=ServerResponse)
async def get_server(server_id: UUID, db: Session = Depends(get_db)):
    """Get details of a specific geoserver."""
    server = db.query(Geoserver).filter(Geoserver.id == server_id).first()
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server {server_id} not found",
        )
    return server


@router.put("/{server_id}", response_model=ServerResponse)
async def update_server(
    server_id: UUID,
    server_update: ServerUpdate,
    db: Session = Depends(get_db),
):
    """Update a geoserver's configuration."""
    server = db.query(Geoserver).filter(Geoserver.id == server_id).first()
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server {server_id} not found",
        )

    # Update fields
    update_data = server_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(server, field, value)

    db.commit()
    db.refresh(server)

    return server


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(server_id: UUID, db: Session = Depends(get_db)):
    """Remove a geoserver from the registry."""
    server = db.query(Geoserver).filter(Geoserver.id == server_id).first()
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server {server_id} not found",
        )

    db.delete(server)
    db.commit()


@router.post("/{server_id}/crawl", response_model=CrawlJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_crawl(server_id: UUID, db: Session = Depends(get_db)):
    """
    Trigger an async discovery/crawl job for this server.

    Creates a background job that discovers all datasets on the server.
    Poll GET /api/v1/servers/crawl/{job_id} for progress updates.
    """
    server = db.query(Geoserver).filter(Geoserver.id == server_id).first()
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server {server_id} not found",
        )

    # Only ArcGIS is currently supported
    if server.provider_type != ProviderType.ARCGIS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Crawling not yet implemented for {server.provider_type}",
        )

    # Create crawl job
    job = CrawlJob(
        geoserver_id=server.id,
        status=JobStatus.PENDING,
        current_stage="pending",
        services_processed=0,
        datasets_discovered=0,
        datasets_new=0,
        datasets_updated=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    logger.info(f"Created crawl job {job.id} for server {server_id}")

    return CrawlJobResponse(
        id=job.id,
        geoserver_id=job.geoserver_id,
        status=job.status.value,
        progress=0.0,
        total_services=job.total_services,
        services_processed=job.services_processed,
        datasets_discovered=job.datasets_discovered,
        datasets_new=job.datasets_new,
        datasets_updated=job.datasets_updated,
        current_stage=job.current_stage,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error=job.error,
    )


@router.get("/{server_id}/crawl/latest", response_model=CrawlJobResponse)
async def get_latest_crawl_job(server_id: UUID, db: Session = Depends(get_db)):
    """Get the most recent crawl job for a server (for resuming progress tracking)."""
    job = (
        db.query(CrawlJob)
        .filter(CrawlJob.geoserver_id == server_id)
        .order_by(CrawlJob.created_at.desc())
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No crawl jobs found for server {server_id}",
        )

    progress = None

    return CrawlJobResponse(
        id=job.id,
        geoserver_id=job.geoserver_id,
        status=job.status.value,
        progress=progress,
        total_services=job.total_services,
        services_processed=job.services_processed,
        datasets_discovered=job.datasets_discovered,
        datasets_new=job.datasets_new,
        datasets_updated=job.datasets_updated,
        current_stage=job.current_stage,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error=job.error,
    )


@router.get("/crawl/{job_id}", response_model=CrawlJobResponse)
async def get_crawl_status(job_id: UUID, db: Session = Depends(get_db)):
    """Get the status and progress of a crawl job."""
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job {job_id} not found",
        )

    # Note: We don't calculate progress percentage for crawl jobs because
    # we don't know the total number of datasets upfront (only services).
    # services_processed is an estimate based on datasets_discovered / 5.
    # Better to show actual dataset count than misleading percentage.
    progress = None

    return CrawlJobResponse(
        id=job.id,
        geoserver_id=job.geoserver_id,
        status=job.status.value,
        progress=progress,
        total_services=job.total_services,
        services_processed=job.services_processed,
        datasets_discovered=job.datasets_discovered,
        datasets_new=job.datasets_new,
        datasets_updated=job.datasets_updated,
        current_stage=job.current_stage,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error=job.error,
    )


@router.get("/{server_id}/health")
async def check_health(server_id: UUID, db: Session = Depends(get_db)):
    """
    Check the health status of a geoserver.

    This performs a quick health check and updates the status.
    """
    server = db.query(Geoserver).filter(Geoserver.id == server_id).first()
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server {server_id} not found",
        )

    # TODO: Implement actual health check using adapter
    return {
        "server_id": server_id,
        "health_status": server.health_status,
        "last_crawl": server.last_crawl,
    }
