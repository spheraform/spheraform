"""Server management endpoints."""

from typing import List
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas import ServerCreate, ServerUpdate, ServerResponse
from spheraform_core.models import Geoserver, HealthStatus, Dataset, ProviderType
from spheraform_core.adapters import ArcGISAdapter

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


@router.post("/{server_id}/crawl")
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

    # Only ArcGIS is currently supported
    if server.provider_type != ProviderType.ARCGIS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Crawling not yet implemented for {server.provider_type}",
        )

    start_time = datetime.utcnow()
    datasets_new = 0
    datasets_updated = 0

    try:
        # Create adapter with connection config and proxy support
        # Use server's country field for proxy selection
        async with ArcGISAdapter(
            base_url=server.base_url,
            connection_config=server.connection_config,
            country_hint=server.country,
        ) as adapter:
            # Discover datasets
            async for dataset_meta in adapter.discover_datasets():
                # Check if dataset already exists
                existing = (
                    db.query(Dataset)
                    .filter(
                        Dataset.geoserver_id == server.id,
                        Dataset.external_id == dataset_meta.external_id,
                    )
                    .first()
                )

                if existing:
                    # Update existing dataset
                    existing.name = dataset_meta.name
                    existing.description = dataset_meta.description
                    existing.access_url = dataset_meta.access_url
                    existing.feature_count = dataset_meta.feature_count
                    existing.bbox = dataset_meta.bbox
                    existing.themes = dataset_meta.themes
                    existing.updated_at = datetime.utcnow()
                    datasets_updated += 1
                else:
                    # Create new dataset
                    new_dataset = Dataset(
                        geoserver_id=server.id,
                        external_id=dataset_meta.external_id,
                        name=dataset_meta.name,
                        description=dataset_meta.description,
                        access_url=dataset_meta.access_url,
                        feature_count=dataset_meta.feature_count,
                        bbox=dataset_meta.bbox,
                        themes=dataset_meta.themes or [],
                        is_active=True,
                    )
                    db.add(new_dataset)
                    datasets_new += 1

            # Update server metadata
            server.last_crawl = datetime.utcnow()
            server.dataset_count = db.query(Dataset).filter(Dataset.geoserver_id == server.id).count()
            server.active_dataset_count = (
                db.query(Dataset)
                .filter(Dataset.geoserver_id == server.id, Dataset.is_active == True)
                .count()
            )
            server.health_status = HealthStatus.HEALTHY

            db.commit()

            duration = (datetime.utcnow() - start_time).total_seconds()

            return {
                "server_id": server_id,
                "datasets_discovered": datasets_new + datasets_updated,
                "datasets_new": datasets_new,
                "datasets_updated": datasets_updated,
                "crawl_duration_seconds": duration,
            }

    except Exception as e:
        server.health_status = HealthStatus.OFFLINE
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Crawl failed: {str(e)}",
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
