"""add_progress_tracking

Revision ID: 003_progress_tracking
Revises: 002_enriched_metadata
Create Date: 2025-12-09 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


# revision identifiers, used by Alembic.
revision = '003_progress_tracking'
down_revision = '002_enriched_metadata'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Note: job_status enum already exists from previous migrations, so we use postgresql.ENUM with existing_type parameter
    # Create crawl_jobs table
    op.create_table('crawl_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('geoserver_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'running', 'completed', 'failed', 'cancelled', name='job_status', create_type=False), nullable=False),
        sa.Column('total_services', sa.Integer(), nullable=True),
        sa.Column('services_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('datasets_discovered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('datasets_new', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('datasets_updated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_stage', sa.String(length=100), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['geoserver_id'], ['geoservers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_crawl_jobs_geoserver_id', 'crawl_jobs', ['geoserver_id'])
    op.create_index('ix_crawl_jobs_status', 'crawl_jobs', ['status'])

    # Add progress tracking fields to download_jobs
    op.add_column('download_jobs', sa.Column('current_stage', sa.String(length=100), nullable=True))
    op.add_column('download_jobs', sa.Column('features_downloaded', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('download_jobs', sa.Column('features_stored', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('download_jobs', sa.Column('total_features', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Remove fields from download_jobs
    op.drop_column('download_jobs', 'total_features')
    op.drop_column('download_jobs', 'features_stored')
    op.drop_column('download_jobs', 'features_downloaded')
    op.drop_column('download_jobs', 'current_stage')

    # Drop crawl_jobs table
    op.drop_index('ix_crawl_jobs_status', 'crawl_jobs')
    op.drop_index('ix_crawl_jobs_geoserver_id', 'crawl_jobs')
    op.drop_table('crawl_jobs')
