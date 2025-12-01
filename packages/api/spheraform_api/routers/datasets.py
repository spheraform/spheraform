"""Dataset endpoints."""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas import DatasetResponse
from spheraform_core.models import Dataset

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
async def preview_dataset(dataset_id: UUID, db: Session = Depends(get_db)):
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

    # TODO: Implement preview fetching using adapter
    return {
        "type": "FeatureCollection",
        "features": [],
        "properties": {
            "dataset_id": str(dataset_id),
            "name": dataset.name,
            "sample": True,
        },
    }


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
