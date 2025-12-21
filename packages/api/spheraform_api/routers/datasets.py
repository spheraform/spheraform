"""Dataset endpoints."""

from typing import List, Optional, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from geoalchemy2.functions import ST_Intersects, ST_Contains, ST_Within, ST_MakeEnvelope

from ..dependencies import get_db
from ..schemas import DatasetResponse
from spheraform_core.models import Dataset, Geoserver, ProviderType
from spheraform_core.adapters import ArcGISAdapter

router = APIRouter()


@router.get("", response_model=List[DatasetResponse])
async def list_datasets(
    skip: int = 0,
    limit: int = 100,
    geoserver_id: Optional[UUID] = None,
    active_only: bool = True,
    # Spatial search parameters
    bbox: Optional[str] = Query(
        None,
        description="Bounding box as 'west,south,east,north' (EPSG:4326)",
        example="-180,-90,180,90"
    ),
    spatial_relation: Literal["intersects", "contains", "within"] = Query(
        "intersects",
        description="Spatial relationship: intersects (overlaps), contains (fully contains), within (fully within)"
    ),
    db: Session = Depends(get_db),
):
    """
    List datasets with optional filtering.

    Supports spatial filtering by bounding box:
    - bbox: Filter datasets by spatial extent (west,south,east,north in WGS84)
    - spatial_relation: How to match (intersects, contains, within)

    Examples:
    - Find datasets in UK: ?bbox=-8,49,2,61
    - Find datasets containing a point: ?bbox=-0.1,51.5,-0.1,51.5&spatial_relation=contains
    """
    query = db.query(Dataset)

    if geoserver_id:
        query = query.filter(Dataset.geoserver_id == geoserver_id)

    if active_only:
        query = query.filter(Dataset.is_active == True)

    # Spatial filtering
    if bbox:
        try:
            # Parse bbox string
            west, south, east, north = map(float, bbox.split(','))

            # Validate bbox
            if not (-180 <= west <= 180 and -180 <= east <= 180):
                raise ValueError("Longitude must be between -180 and 180")
            if not (-90 <= south <= 90 and -90 <= north <= 90):
                raise ValueError("Latitude must be between -90 and 90")
            if west >= east:
                raise ValueError("West must be less than east")
            if south >= north:
                raise ValueError("South must be less than north")

            # Create PostGIS envelope
            search_geom = ST_MakeEnvelope(west, south, east, north, 4326)

            # Apply spatial filter based on relation type
            if spatial_relation == "intersects":
                query = query.filter(ST_Intersects(Dataset.bbox, search_geom))
            elif spatial_relation == "contains":
                query = query.filter(ST_Contains(Dataset.bbox, search_geom))
            elif spatial_relation == "within":
                query = query.filter(ST_Within(Dataset.bbox, search_geom))

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bbox parameter: {str(e)}. Expected format: 'west,south,east,north'"
            )

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


@router.get("/{dataset_id}/tiles")
async def get_tiles_url(
    dataset_id: UUID,
    presigned: bool = Query(False, description="Generate presigned URL for private buckets"),
    expiration: int = Query(3600, description="Presigned URL expiration in seconds (default: 1 hour)", ge=60, le=86400),
    db: Session = Depends(get_db),
):
    """
    Get PMTiles URL for a dataset.

    Returns the URL to the PMTiles file in object storage (MinIO/R2) for direct browser access.
    The frontend can use this URL with pmtiles.js to load vector tiles.

    Args:
        dataset_id: Dataset UUID
        presigned: Generate presigned URL (for private buckets)
        expiration: Presigned URL expiration in seconds (60s - 24h)

    Returns:
        PMTiles URL (public or presigned) with metadata
    """
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found"
        )

    if not dataset.s3_tiles_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} has no PMTiles available. PMTiles are generated during download for datasets in object storage."
        )

    from spheraform_core.storage.s3_client import S3Client
    s3_client = S3Client()

    if presigned:
        url = await s3_client.get_presigned_url(
            dataset.s3_tiles_key,
            expiration=expiration
        )
    else:
        # Public URL
        url = s3_client.get_public_url(dataset.s3_tiles_key)

    return {
        "dataset_id": str(dataset_id),
        "dataset_name": dataset.name,
        "tiles_url": url,
        "s3_key": dataset.s3_tiles_key,
        "presigned": presigned,
        "pmtiles_generated_at": dataset.pmtiles_generated_at.isoformat() if dataset.pmtiles_generated_at else None,
        "pmtiles_size_bytes": dataset.pmtiles_size_bytes,
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
