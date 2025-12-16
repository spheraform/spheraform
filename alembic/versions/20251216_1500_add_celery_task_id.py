"""add_celery_task_id

Revision ID: 006_celery_task_id
Revises: 005_max_record_count
Create Date: 2025-12-16 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006_celery_task_id'
down_revision = '005_max_record_count'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add celery_task_id column to job tables for tracking distributed tasks
    # This allows us to link database job records to Celery task execution

    op.add_column('download_jobs', sa.Column('celery_task_id', sa.String(255), nullable=True))
    op.add_column('crawl_jobs', sa.Column('celery_task_id', sa.String(255), nullable=True))
    op.add_column('export_jobs', sa.Column('celery_task_id', sa.String(255), nullable=True))

    # Create indexes for efficient task lookups
    op.create_index('ix_download_jobs_celery_task_id', 'download_jobs', ['celery_task_id'])
    op.create_index('ix_crawl_jobs_celery_task_id', 'crawl_jobs', ['celery_task_id'])
    op.create_index('ix_export_jobs_celery_task_id', 'export_jobs', ['celery_task_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_export_jobs_celery_task_id', 'export_jobs')
    op.drop_index('ix_crawl_jobs_celery_task_id', 'crawl_jobs')
    op.drop_index('ix_download_jobs_celery_task_id', 'download_jobs')

    # Drop celery_task_id columns
    op.drop_column('export_jobs', 'celery_task_id')
    op.drop_column('crawl_jobs', 'celery_task_id')
    op.drop_column('download_jobs', 'celery_task_id')
