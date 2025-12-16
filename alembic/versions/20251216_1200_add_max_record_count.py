"""add_max_record_count

Revision ID: 005_max_record_count
Revises: 004_s3_storage
Create Date: 2025-12-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005_max_record_count'
down_revision = '004_s3_storage'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add max_record_count column for pagination limits (from ArcGIS, WFS, OGC API, etc.)
    op.add_column('datasets', sa.Column('max_record_count', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Drop max_record_count column
    op.drop_column('datasets', 'max_record_count')
