"""Server management endpoints."""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas import ServerCreate, ServerUpdate, ServerResponse
from spheraform_core.models import Geoserver, HealthStatus

router = APIRouter()


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


@router.post("/{server_id}/crawl", status_code=status.HTTP_202_ACCEPTED)
async def trigger_crawl(server_id: UUID, db: Session = Depends(get_db)):
    """
    Trigger a discovery/crawl job for this server.

    This will discover all datasets on the server and add them to the catalogue.
    """
    server = db.query(Geoserver).filter(Geoserver.id == server_id).first()
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server {server_id} not found",
        )

    # TODO: Trigger crawl job (will implement with Dagster/Celery)
    return {"message": "Crawl job queued", "server_id": server_id}


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
