"""add_pmtiles_tracking

Revision ID: 007_pmtiles_tracking
Revises: 006_celery_task_id
Create Date: 2025-12-21 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007_pmtiles_tracking'
down_revision = '006_celery_task_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add PMTiles tracking fields to datasets table
    # These fields track whether PMTiles have been generated for each dataset
    # and when they were created, enabling cloud-native tile serving

    op.add_column('datasets', sa.Column('pmtiles_generated', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('datasets', sa.Column('pmtiles_generated_at', sa.DateTime(), nullable=True))
    op.add_column('datasets', sa.Column('pmtiles_size_bytes', sa.Integer(), nullable=True))

    # Create index for querying datasets by PMTiles generation status
    op.create_index('ix_datasets_pmtiles_generated', 'datasets', ['pmtiles_generated'])


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_datasets_pmtiles_generated', 'datasets')

    # Drop PMTiles tracking columns
    op.drop_column('datasets', 'pmtiles_size_bytes')
    op.drop_column('datasets', 'pmtiles_generated_at')
    op.drop_column('datasets', 'pmtiles_generated')
