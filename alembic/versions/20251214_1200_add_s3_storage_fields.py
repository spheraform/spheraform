"""add_s3_storage_fields

Revision ID: 004_s3_storage
Revises: 003_progress_tracking
Create Date: 2025-12-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '004_s3_storage'
down_revision = '003_progress_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create storage_format enum
    storage_format_enum = postgresql.ENUM(
        'postgis', 'geoparquet', 'hybrid',
        name='storage_format',
        create_type=True
    )
    storage_format_enum.create(op.get_bind(), checkfirst=True)

    # Add S3 storage fields to datasets table
    op.add_column('datasets', sa.Column(
        'storage_format',
        postgresql.ENUM('postgis', 'geoparquet', 'hybrid', name='storage_format', create_type=False),
        nullable=False,
        server_default='postgis'
    ))

    op.add_column('datasets', sa.Column(
        'use_s3_storage',
        sa.Boolean(),
        nullable=False,
        server_default='false'
    ))

    op.add_column('datasets', sa.Column(
        's3_data_key',
        sa.String(length=500),
        nullable=True
    ))

    op.add_column('datasets', sa.Column(
        's3_tiles_key',
        sa.String(length=500),
        nullable=True
    ))

    op.add_column('datasets', sa.Column(
        'parquet_schema',
        sa.Text(),
        nullable=True
    ))

    op.add_column('datasets', sa.Column(
        'parquet_row_groups',
        sa.Integer(),
        nullable=True
    ))

    # Create indexes for S3 storage fields
    op.create_index('ix_datasets_storage_format', 'datasets', ['storage_format'])
    op.create_index('ix_datasets_use_s3_storage', 'datasets', ['use_s3_storage'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_datasets_use_s3_storage', 'datasets')
    op.drop_index('ix_datasets_storage_format', 'datasets')

    # Remove S3 storage fields from datasets table
    op.drop_column('datasets', 'parquet_row_groups')
    op.drop_column('datasets', 'parquet_schema')
    op.drop_column('datasets', 's3_tiles_key')
    op.drop_column('datasets', 's3_data_key')
    op.drop_column('datasets', 'use_s3_storage')
    op.drop_column('datasets', 'storage_format')

    # Drop storage_format enum
    storage_format_enum = postgresql.ENUM(name='storage_format')
    storage_format_enum.drop(op.get_bind(), checkfirst=True)
