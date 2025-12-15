#!/usr/bin/env python3
"""
Migration script to move datasets from PostGIS to S3 storage.

Usage:
    # Migrate single dataset
    python scripts/migrate_postgis_to_s3.py --dataset-id <uuid>

    # Migrate all datasets in batches
    python scripts/migrate_postgis_to_s3.py --batch-size 10

    # Dry run
    python scripts/migrate_postgis_to_s3.py --dry-run
"""

import argparse
import asyncio
import logging
import sys
import tempfile
from pathlib import Path
from uuid import UUID

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from spheraform_core.config import get_settings
from spheraform_core.models import Dataset
from spheraform_core.storage.backend import PostGISStorageBackend, S3StorageBackend

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def export_postgis_to_geojson(db: Session, dataset: Dataset, output_path: Path) -> None:
    """Export PostGIS dataset to GeoJSON file."""
    if not dataset.cache_table:
        raise ValueError(f"Dataset {dataset.id} has no cache_table")

    logger.info(f"Exporting {dataset.cache_table} to GeoJSON...")

    # Query PostGIS table and export as GeoJSON
    query = text(f"""
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', jsonb_agg(
                jsonb_build_object(
                    'type', 'Feature',
                    'geometry', ST_AsGeoJSON(ST_Transform(geom, 4326))::jsonb,
                    'properties', properties
                )
            )
        )
        FROM {dataset.cache_table}
    """)

    result = db.execute(query).scalar()

    # Write to file
    import json

    if result is None:
        result = {"type": "FeatureCollection", "features": []}

    with open(output_path, "w") as f:
        json.dump(result, f)

    logger.info(f"Exported {dataset.feature_count or 0} features to {output_path}")


async def migrate_dataset(
    db: Session,
    dataset_id: UUID,
    dry_run: bool = False,
    keep_postgis: bool = True,
) -> bool:
    """
    Migrate single dataset from PostGIS to S3.

    Args:
        db: Database session
        dataset_id: Dataset UUID
        dry_run: If True, don't actually migrate
        keep_postgis: If True, keep PostGIS table for rollback

    Returns:
        True if migration succeeded, False otherwise
    """
    # Get dataset
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()

    if not dataset:
        logger.error(f"Dataset {dataset_id} not found")
        return False

    # Check if already migrated
    if dataset.use_s3_storage:
        logger.info(f"Dataset {dataset.name} already uses S3 storage, skipping")
        return True

    # Check if cached in PostGIS
    if not dataset.is_cached or not dataset.cache_table:
        logger.warning(f"Dataset {dataset.name} is not cached in PostGIS, skipping")
        return False

    logger.info(f"Migrating dataset: {dataset.name}")
    logger.info(f"  Features: {dataset.feature_count or 'unknown'}")
    logger.info(f"  PostGIS table: {dataset.cache_table}")

    if dry_run:
        logger.info("  [DRY RUN] Would migrate to S3")
        return True

    try:
        # Create temporary GeoJSON file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".geojson", delete=False
        ) as temp_file:
            temp_path = Path(temp_file.name)

        # Export from PostGIS
        await export_postgis_to_geojson(db, dataset, temp_path)

        # Store in S3
        s3_backend = S3StorageBackend(db)
        storage_result = await s3_backend.store_dataset(
            dataset_id=dataset_id,
            geojson_path=temp_path,
            job_id=None,
        )

        # Update dataset metadata
        dataset.use_s3_storage = True
        dataset.storage_format = "geoparquet"
        dataset.s3_data_key = storage_result["s3_data_key"]
        dataset.s3_tiles_key = storage_result["s3_tiles_key"]
        dataset.parquet_schema = storage_result.get("parquet_schema")

        if not keep_postgis:
            # Drop PostGIS table
            logger.info(f"Dropping PostGIS table {dataset.cache_table}")
            db.execute(text(f"DROP TABLE IF EXISTS {dataset.cache_table}"))
            dataset.cache_table = None

        db.commit()

        # Clean up temp file
        temp_path.unlink(missing_ok=True)

        logger.info(f"✓ Successfully migrated {dataset.name} to S3")
        logger.info(f"  GeoParquet: {storage_result['s3_data_key']}")
        logger.info(f"  PMTiles: {storage_result['s3_tiles_key']}")

        return True

    except Exception as e:
        logger.exception(f"✗ Failed to migrate {dataset.name}: {e}")
        db.rollback()
        return False


async def migrate_all(
    db: Session,
    batch_size: int = 10,
    dry_run: bool = False,
    min_features: int = 0,
    max_features: int = None,
) -> None:
    """
    Migrate all PostGIS datasets to S3 in batches.

    Args:
        db: Database session
        batch_size: Number of datasets to migrate in parallel
        dry_run: If True, don't actually migrate
        min_features: Only migrate datasets with >= this many features
        max_features: Only migrate datasets with <= this many features
    """
    # Query all datasets cached in PostGIS
    query = select(Dataset).where(
        Dataset.is_cached == True,
        Dataset.use_s3_storage == False,
        Dataset.cache_table.isnot(None),
    )

    if min_features:
        query = query.where(Dataset.feature_count >= min_features)

    if max_features:
        query = query.where(Dataset.feature_count <= max_features)

    query = query.order_by(Dataset.feature_count.desc())

    datasets = db.execute(query).scalars().all()

    total = len(datasets)
    logger.info(f"Found {total} datasets to migrate")

    if total == 0:
        logger.info("No datasets to migrate")
        return

    succeeded = 0
    failed = 0

    # Process in batches
    for i in range(0, total, batch_size):
        batch = datasets[i : i + batch_size]
        logger.info(f"\n=== Processing batch {i // batch_size + 1} ({len(batch)} datasets) ===")

        # Migrate batch in parallel
        tasks = [migrate_dataset(db, dataset.id, dry_run=dry_run) for dataset in batch]
        results = await asyncio.gather(*tasks)

        succeeded += sum(results)
        failed += len(results) - sum(results)

        logger.info(f"Batch complete: {sum(results)}/{len(batch)} succeeded")

    logger.info(f"\n=== Migration Summary ===")
    logger.info(f"Total: {total}")
    logger.info(f"Succeeded: {succeeded}")
    logger.info(f"Failed: {failed}")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate datasets from PostGIS to S3 storage"
    )
    parser.add_argument(
        "--dataset-id",
        type=UUID,
        help="Migrate single dataset by ID",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of datasets to migrate in parallel (default: 10)",
    )
    parser.add_argument(
        "--min-features",
        type=int,
        default=0,
        help="Only migrate datasets with >= this many features (default: 0)",
    )
    parser.add_argument(
        "--max-features",
        type=int,
        help="Only migrate datasets with <= this many features",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run - don't actually migrate",
    )
    parser.add_argument(
        "--drop-postgis",
        action="store_true",
        help="Drop PostGIS tables after migration (default: keep for rollback)",
    )

    args = parser.parse_args()

    # Setup database connection
    settings = get_settings()
    engine = create_engine(settings.database_url)

    with Session(engine) as db:
        if args.dataset_id:
            # Migrate single dataset
            asyncio.run(
                migrate_dataset(
                    db,
                    args.dataset_id,
                    dry_run=args.dry_run,
                    keep_postgis=not args.drop_postgis,
                )
            )
        else:
            # Migrate all datasets
            asyncio.run(
                migrate_all(
                    db,
                    batch_size=args.batch_size,
                    dry_run=args.dry_run,
                    min_features=args.min_features,
                    max_features=args.max_features,
                )
            )


if __name__ == "__main__":
    main()
