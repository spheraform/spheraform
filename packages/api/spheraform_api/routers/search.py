"""Search endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from geoalchemy2.functions import ST_Intersects, ST_Buffer, ST_MakePoint

from ..dependencies import get_db
from ..schemas import SearchRequest, SearchResponse, DatasetResponse
from spheraform_core.models import Dataset

router = APIRouter()


@router.post("", response_model=SearchResponse)
async def search_datasets(request: SearchRequest, db: Session = Depends(get_db)):
    """
    Search for datasets by location, text, themes, etc.

    Supports spatial search, full-text search, and filtering by themes/formats.
    """
    query = db.query(Dataset).filter(Dataset.is_active == True)

    # Spatial search
    if request.geometry:
        # TODO: Parse GeoJSON geometry and create spatial filter
        pass

    elif request.point and request.buffer_km:
        # Create point with buffer
        lon, lat = request.point
        point_geom = ST_MakePoint(lon, lat)
        buffer_geom = ST_Buffer(point_geom, request.buffer_km * 1000)  # Convert km to meters

        query = query.filter(ST_Intersects(Dataset.bbox, buffer_geom))

    # Text search (simple version - can be improved with full-text search)
    if request.text:
        search_term = f"%{request.text}%"
        query = query.filter(
            or_(
                Dataset.name.ilike(search_term),
                Dataset.description.ilike(search_term),
                Dataset.keywords.any(search_term),
            )
        )

    # Filter by themes
    if request.themes:
        query = query.filter(Dataset.themes.overlap(request.themes))

    # Filter by cached status
    if request.cached_only:
        query = query.filter(Dataset.is_cached == True)

    # Filter by update date
    if request.updated_after:
        query = query.filter(Dataset.updated_date >= request.updated_after)

    # Get total count before pagination
    total = query.count()

    # Apply pagination
    datasets = query.offset(request.offset).limit(request.limit).all()

    # Calculate facets (for UI filtering)
    facets = {}

    # Theme facets
    if not request.themes:
        theme_facets = (
            db.query(func.unnest(Dataset.themes).label("theme"), func.count())
            .filter(Dataset.is_active == True)
            .group_by("theme")
            .all()
        )
        facets["themes"] = {theme: count for theme, count in theme_facets}

    return SearchResponse(
        total=total,
        datasets=datasets,
        facets=facets,
    )
