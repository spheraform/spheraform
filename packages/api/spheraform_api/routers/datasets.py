"""Dataset endpoints."""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas import DatasetResponse
from spheraform_core.models import Dataset, Geoserver, ProviderType
from spheraform_core.adapters import ArcGISAdapter

router = APIRouter()


@router.get("", response_model=List[DatasetResponse])
async def list_datasets(
    skip: int = 0,
    limit: int = 100,
    geoserver_id: UUID = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    """List datasets with optional filtering."""
    query = db.query(Dataset)

    if geoserver_id:
        query = query.filter(Dataset.geoserver_id == geoserver_id)

    if active_only:
        query = query.filter(Dataset.is_active == True)

    datasets = query.offset(skip).limit(limit).all()
    return datasets


@router.get("/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(dataset_id: UUID, db: Session = Depends(get_db)):
    """Get details of a specific dataset."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found",
        )
    return dataset


@router.get("/{dataset_id}/preview")
async def preview_dataset(dataset_id: UUID, limit: int = 100, db: Session = Depends(get_db)):
    """
    Get a preview of the dataset (sample features as GeoJSON).

    Returns a small sample of features for map preview.
    """
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found",
        )

    # Get the associated geoserver
    geoserver = db.query(Geoserver).filter(Geoserver.id == dataset.geoserver_id).first()
    if not geoserver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Geoserver not found for dataset {dataset_id}",
        )

    # Only ArcGIS is currently supported
    if geoserver.provider_type != ProviderType.ARCGIS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Preview not yet implemented for {geoserver.provider_type}",
        )

    try:
        # Create adapter with connection config and proxy support
        async with ArcGISAdapter(
            base_url=geoserver.base_url,
            connection_config=geoserver.connection_config,
            country_hint=geoserver.country,
        ) as adapter:
            # Fetch preview using the dataset's access_url
            geojson = await adapter.get_preview(dataset.access_url, limit=limit)

            if geojson is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to fetch preview from source",
                )

            # Add metadata to the response
            if "properties" not in geojson:
                geojson["properties"] = {}

            geojson["properties"].update({
                "dataset_id": str(dataset_id),
                "name": dataset.name,
                "sample": True,
                "limit": limit,
            })

            return geojson

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preview failed: {str(e)}",
        )


@router.post("/{dataset_id}/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_dataset(dataset_id: UUID, db: Session = Depends(get_db)):
    """
    Force re-sync of a dataset from its source.

    This triggers a download job to refresh the cached data.
    """
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found",
        )

    # TODO: Queue download job
    return {"message": "Refresh job queued", "dataset_id": dataset_id}
