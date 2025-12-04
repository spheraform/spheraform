"""Configuration management using pydantic-settings."""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform",
        description="PostgreSQL connection URL",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for job queue",
    )

    # Object Storage (MinIO/S3)
    s3_endpoint: str = Field(
        default="http://localhost:9000",
        description="S3-compatible storage endpoint",
    )
    s3_access_key: str = Field(default="minioadmin", description="S3 access key")
    s3_secret_key: str = Field(default="minioadmin", description="S3 secret key")
    s3_bucket: str = Field(default="geodata", description="S3 bucket name")
    s3_region: str = Field(default="us-east-1", description="S3 region")

    # Paths
    data_dir: str = Field(
        default="/tmp/spheraform/data", description="Local data directory"
    )
    temp_dir: str = Field(
        default="/tmp/spheraform/temp", description="Temporary files directory"
    )

    # External services
    martin_url: str = Field(
        default="http://localhost:3000", description="Martin tile server URL"
    )

    # Application defaults
    default_probe_frequency_hours: int = Field(
        default=24, description="Default hours between change probes"
    )
    default_download_timeout: int = Field(
        default=300, description="Default download timeout in seconds"
    )
    max_concurrent_downloads_per_server: int = Field(
        default=5, description="Max parallel downloads per server"
    )
    max_chunk_parallel: int = Field(
        default=10, description="Max parallel chunk downloads"
    )

    # Security
    encryption_key: str = Field(
        default="change-this-to-a-secure-32-byte-base64-encoded-key",
        description="Encryption key for credentials",
    )

    # API settings
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_workers: int = Field(default=4, description="Number of API workers")
    api_reload: bool = Field(default=False, description="Enable auto-reload in dev")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")


# Global settings instance
settings = Settings()
