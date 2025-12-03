"""add_country_to_geoserver

Revision ID: e0bf894d086d
Revises: 001_initial
Create Date: 2025-12-03 19:06:36.312422

"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2


# revision identifiers, used by Alembic.
revision = 'e0bf894d086d'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add country column to geoservers table
    # Supports single or comma-separated country codes (e.g. "GB" or "BE,NL,LU")
    op.add_column('geoservers', sa.Column('country', sa.String(length=50), nullable=True))


def downgrade() -> None:
    # Remove country column
    op.drop_column('geoservers', 'country')
