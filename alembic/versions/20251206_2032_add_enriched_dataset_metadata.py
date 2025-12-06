"""add_enriched_dataset_metadata

Revision ID: 002_enriched_metadata
Revises: e0bf894d086d
Create Date: 2025-12-06 20:32:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP


# revision identifiers, used by Alembic.
revision = '002_enriched_metadata'
down_revision = 'e0bf894d086d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add serviceItemId (the true unique identifier for ArcGIS datasets)
    op.add_column('datasets', sa.Column('service_item_id', sa.String(length=255), nullable=True))

    # Add geometry type (Point, LineString, Polygon, etc.)
    op.add_column('datasets', sa.Column('geometry_type', sa.String(length=50), nullable=True))

    # Add source SRID/WKID (coordinate system identifier)
    op.add_column('datasets', sa.Column('source_srid', sa.Integer(), nullable=True))

    # Add last edit date from source (if available)
    op.add_column('datasets', sa.Column('last_edit_date', TIMESTAMP(timezone=True), nullable=True))

    # Add last fetched date (when dataset was actually downloaded/cached, distinct from crawl)
    op.add_column('datasets', sa.Column('last_fetched_at', TIMESTAMP(timezone=True), nullable=True))

    # Create index on service_item_id for faster lookups
    op.create_index('ix_datasets_service_item_id', 'datasets', ['service_item_id'])

    # Create index on geometry_type for filtering
    op.create_index('ix_datasets_geometry_type', 'datasets', ['geometry_type'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_datasets_geometry_type', table_name='datasets')
    op.drop_index('ix_datasets_service_item_id', table_name='datasets')

    # Drop columns
    op.drop_column('datasets', 'last_fetched_at')
    op.drop_column('datasets', 'last_edit_date')
    op.drop_column('datasets', 'source_srid')
    op.drop_column('datasets', 'geometry_type')
    op.drop_column('datasets', 'service_item_id')
