#!/usr/bin/env python3
"""
Cleanup script to remove PostGIS cache tables for datasets migrated to S3.

Usage:
    # Remove PostGIS tables for datasets migrated 30+ days ago
    python scripts/cleanup_postgis_cache.py --min-days 30

    # Dry run
    python scripts/cleanup_postgis_cache.py --dry-run

    # Remove all PostGIS tables for S3-migrated datasets
    python scripts/cleanup_postgis_cache.py --min-days 0
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from spheraform_core.config import get_settings
from spheraform_core.models import Dataset

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def cleanup_dataset(db: Session, dataset: Dataset, dry_run: bool = False) -> bool:
    """
    Remove PostGIS table for a migrated dataset.

    Args:
        db: Database session
        dataset: Dataset object
        dry_run: If True, don't actually delete

    Returns:
        True if cleanup succeeded, False otherwise
    """
    if not dataset.cache_table:
        logger.warning(f"Dataset {dataset.name} has no cache_table, skipping")
        return False

    logger.info(f"Cleaning up dataset: {dataset.name}")
    logger.info(f"  PostGIS table: {dataset.cache_table}")
    logger.info(f"  S3 data: {dataset.s3_data_key}")
    logger.info(f"  S3 tiles: {dataset.s3_tiles_key}")

    if dry_run:
        logger.info("  [DRY RUN] Would drop table")
        return True

    try:
        # Check if table exists
        check_query = text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = :table_name
            )
        """)

        exists = db.execute(
            check_query, {"table_name": dataset.cache_table}
        ).scalar()

        if not exists:
            logger.warning(f"  Table {dataset.cache_table} does not exist, skipping")
            # Clear cache_table reference
            dataset.cache_table = None
            db.commit()
            return True

        # Drop table
        logger.info(f"  Dropping table {dataset.cache_table}")
        db.execute(text(f"DROP TABLE IF EXISTS {dataset.cache_table} CASCADE"))

        # Clear cache_table reference
        dataset.cache_table = None

        db.commit()

        logger.info(f"✓ Successfully cleaned up {dataset.name}")
        return True

    except Exception as e:
        logger.exception(f"✗ Failed to cleanup {dataset.name}: {e}")
        db.rollback()
        return False


def cleanup_all(
    db: Session,
    min_days: int = 30,
    dry_run: bool = False,
) -> None:
    """
    Cleanup all PostGIS tables for datasets migrated to S3.

    Args:
        db: Database session
        min_days: Only cleanup datasets migrated >= this many days ago
        dry_run: If True, don't actually delete
    """
    # Calculate cutoff date
    cutoff_date = datetime.utcnow() - timedelta(days=min_days)

    # Query all datasets using S3 with PostGIS tables still present
    query = (
        select(Dataset)
        .where(
            Dataset.use_s3_storage == True,
            Dataset.cache_table.isnot(None),
        )
    )

    if min_days > 0:
        query = query.where(Dataset.cached_at <= cutoff_date)

    query = query.order_by(Dataset.cached_at)

    datasets = db.execute(query).scalars().all()

    total = len(datasets)
    logger.info(f"Found {total} datasets to cleanup (migrated >= {min_days} days ago)")

    if total == 0:
        logger.info("No datasets to cleanup")
        return

    succeeded = 0
    failed = 0

    for dataset in datasets:
        if cleanup_dataset(db, dataset, dry_run=dry_run):
            succeeded += 1
        else:
            failed += 1

    logger.info(f"\n=== Cleanup Summary ===")
    logger.info(f"Total: {total}")
    logger.info(f"Succeeded: {succeeded}")
    logger.info(f"Failed: {failed}")

    if not dry_run:
        # Calculate space saved
        logger.info("\n=== Storage Analysis ===")
        logger.info("Run VACUUM FULL to reclaim disk space:")
        logger.info("  psql -U spheraform -d spheraform -c 'VACUUM FULL;'")


def main():
    parser = argparse.ArgumentParser(
        description="Cleanup PostGIS cache tables for datasets migrated to S3"
    )
    parser.add_argument(
        "--min-days",
        type=int,
        default=30,
        help="Only cleanup datasets migrated >= this many days ago (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run - don't actually delete",
    )
    parser.add_argument(
        "--dataset-id",
        type=str,
        help="Cleanup single dataset by ID",
    )

    args = parser.parse_args()

    # Setup database connection
    settings = get_settings()
    engine = create_engine(settings.database_url)

    with Session(engine) as db:
        if args.dataset_id:
            # Cleanup single dataset
            from uuid import UUID

            dataset_id = UUID(args.dataset_id)
            dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()

            if not dataset:
                logger.error(f"Dataset {dataset_id} not found")
                sys.exit(1)

            if not dataset.use_s3_storage:
                logger.error(f"Dataset {dataset.name} is not using S3 storage")
                sys.exit(1)

            cleanup_dataset(db, dataset, dry_run=args.dry_run)
        else:
            # Cleanup all datasets
            cleanup_all(db, min_days=args.min_days, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
