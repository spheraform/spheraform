"""Initial schema

Revision ID: 001_initial
Revises:
Create Date: 2025-12-01 12:41:00.000000

"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create PostGIS extension
    op.execute('CREATE EXTENSION IF NOT EXISTS postgis')

    # Create enums
    op.execute("CREATE TYPE provider_type AS ENUM ('arcgis', 'wfs', 'wcs', 'ckan', 'geoserver', 's3', 'atom', 'opendatasoft', 'direct', 'gee')")
    op.execute("CREATE TYPE health_status AS ENUM ('healthy', 'degraded', 'offline', 'unknown')")
    op.execute("CREATE TYPE download_strategy AS ENUM ('simple', 'paged', 'chunked', 'distributed')")
    op.execute("CREATE TYPE change_check_method AS ENUM ('etag', 'last_modified', 'arcgis_edit_date', 'wfs_update_sequence', 'ckan_modified', 'feature_count', 'sample_checksum', 'metadata_hash')")
    op.execute("CREATE TYPE job_status AS ENUM ('pending', 'running', 'completed', 'failed', 'cancelled')")
    op.execute("CREATE TYPE export_format AS ENUM ('geojson', 'gpkg', 'shp', 'mbtiles', 'pmtiles', 'postgis', 'geoparquet', 'csv', 'kml', 'fgb')")

    # Create themes table
    op.create_table('themes',
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('aliases', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('parent_code', sa.String(length=50), nullable=True),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(['parent_code'], ['themes.code'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('code', name='pk_themes')
    )

    # Create geoservers table
    op.create_table('geoservers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('base_url', sa.Text(), nullable=False),
        sa.Column('provider_type', postgresql.ENUM(name='provider_type', create_type=False), nullable=False),
        sa.Column('auth_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('capabilities', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('health_status', postgresql.ENUM(name='health_status', create_type=False), nullable=False),
        sa.Column('last_crawl', sa.DateTime(timezone=True), nullable=True),
        sa.Column('probe_frequency_hours', sa.Integer(), nullable=False),
        sa.Column('rate_limit_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('connection_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('dataset_count', sa.Integer(), nullable=False),
        sa.Column('active_dataset_count', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('contact_email', sa.String(length=255), nullable=True),
        sa.Column('organization', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_geoservers')
    )

    # Create datasets table
    op.create_table('datasets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('geoserver_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('external_id', sa.String(length=500), nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('keywords', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('themes', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('bbox', geoalchemy2.types.Geometry(geometry_type='POLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('feature_count', sa.Integer(), nullable=True),
        sa.Column('updated_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('download_formats', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('access_url', sa.Text(), nullable=False),
        sa.Column('cached_etag', sa.String(length=255), nullable=True),
        sa.Column('cached_last_modified', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_change_check', sa.DateTime(timezone=True), nullable=True),
        sa.Column('change_detected', sa.Boolean(), nullable=False),
        sa.Column('is_cached', sa.Boolean(), nullable=False),
        sa.Column('cached_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cache_table', sa.String(length=255), nullable=True),
        sa.Column('cache_size_bytes', sa.Integer(), nullable=True),
        sa.Column('download_strategy', postgresql.ENUM(name='download_strategy', create_type=False), nullable=False),
        sa.Column('quality_score', sa.Integer(), nullable=True),
        sa.Column('has_geometry_errors', sa.Boolean(), nullable=False),
        sa.Column('last_validated', sa.DateTime(timezone=True), nullable=True),
        sa.Column('license', sa.String(length=255), nullable=True),
        sa.Column('attribution', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('source_metadata', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['geoserver_id'], ['geoservers.id'], name='fk_datasets_geoserver_id_geoservers', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_datasets')
    )

    # Create indexes for datasets
    op.create_index('ix_datasets_geoserver_id', 'datasets', ['geoserver_id'])
    op.create_index('ix_datasets_is_active', 'datasets', ['is_active'])
    op.create_index('ix_datasets_geoserver_active', 'datasets', ['geoserver_id', 'is_active'])
    op.create_index('ix_datasets_themes', 'datasets', ['themes'], postgresql_using='gin')
    op.create_index('ix_datasets_bbox', 'datasets', ['bbox'], postgresql_using='gist')

    # Create change_checks table
    op.create_table('change_checks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('dataset_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('method', postgresql.ENUM(name='change_check_method', create_type=False), nullable=False),
        sa.Column('changed', sa.Boolean(), nullable=False),
        sa.Column('conclusive', sa.Boolean(), nullable=False),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('triggered_download', sa.Boolean(), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], name='fk_change_checks_dataset_id_datasets', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_change_checks')
    )

    # Create indexes for change_checks
    op.create_index('ix_change_checks_dataset_id', 'change_checks', ['dataset_id'])
    op.create_index('ix_change_checks_checked_at', 'change_checks', ['checked_at'], postgresql_ops={'checked_at': 'DESC'})
    op.create_index('ix_change_checks_dataset_checked', 'change_checks', ['dataset_id', sa.text('checked_at DESC')])

    # Create download_jobs table
    op.create_table('download_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('dataset_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', postgresql.ENUM(name='job_status', create_type=False), nullable=False),
        sa.Column('strategy', sa.String(length=50), nullable=False),
        sa.Column('total_chunks', sa.Integer(), nullable=True),
        sa.Column('chunks_completed', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('output_path', sa.Text(), nullable=True),
        sa.Column('output_format', sa.String(length=50), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], name='fk_download_jobs_dataset_id_datasets', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_download_jobs')
    )

    # Create indexes for download_jobs
    op.create_index('ix_download_jobs_dataset_id', 'download_jobs', ['dataset_id'])
    op.create_index('ix_download_jobs_status', 'download_jobs', ['status'])

    # Create download_chunks table
    op.create_table('download_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('strategy', sa.String(length=50), nullable=False),
        sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', postgresql.ENUM(name='job_status', create_type=False), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('feature_count', sa.Integer(), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['download_jobs.id'], name='fk_download_chunks_job_id_download_jobs', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_download_chunks')
    )

    # Create indexes for download_chunks
    op.create_index('ix_download_chunks_job_id', 'download_chunks', ['job_id'])
    op.create_index('ix_download_chunks_job_status', 'download_chunks', ['job_id', 'status'])

    # Create export_jobs table
    op.create_table('export_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('dataset_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column('format', postgresql.ENUM(name='export_format', create_type=False), nullable=False),
        sa.Column('clip_geometry', geoalchemy2.types.Geometry(geometry_type='GEOMETRY', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('status', postgresql.ENUM(name='job_status', create_type=False), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('output_path', sa.Text(), nullable=True),
        sa.Column('output_size_bytes', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('user_id', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_export_jobs')
    )

    # Create indexes for export_jobs
    op.create_index('ix_export_jobs_status', 'export_jobs', ['status'])
    op.create_index('ix_export_jobs_expires_at', 'export_jobs', ['expires_at'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('ix_export_jobs_expires_at', table_name='export_jobs')
    op.drop_index('ix_export_jobs_status', table_name='export_jobs')
    op.drop_table('export_jobs')

    op.drop_index('ix_download_chunks_job_status', table_name='download_chunks')
    op.drop_index('ix_download_chunks_job_id', table_name='download_chunks')
    op.drop_table('download_chunks')

    op.drop_index('ix_download_jobs_status', table_name='download_jobs')
    op.drop_index('ix_download_jobs_dataset_id', table_name='download_jobs')
    op.drop_table('download_jobs')

    op.drop_index('ix_change_checks_dataset_checked', table_name='change_checks')
    op.drop_index('ix_change_checks_checked_at', table_name='change_checks')
    op.drop_index('ix_change_checks_dataset_id', table_name='change_checks')
    op.drop_table('change_checks')

    op.drop_index('ix_datasets_bbox', table_name='datasets')
    op.drop_index('ix_datasets_themes', table_name='datasets')
    op.drop_index('ix_datasets_geoserver_active', table_name='datasets')
    op.drop_index('ix_datasets_is_active', table_name='datasets')
    op.drop_index('ix_datasets_geoserver_id', table_name='datasets')
    op.drop_table('datasets')

    op.drop_table('geoservers')
    op.drop_table('themes')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS export_format')
    op.execute('DROP TYPE IF EXISTS job_status')
    op.execute('DROP TYPE IF EXISTS change_check_method')
    op.execute('DROP TYPE IF EXISTS download_strategy')
    op.execute('DROP TYPE IF EXISTS health_status')
    op.execute('DROP TYPE IF EXISTS provider_type')
