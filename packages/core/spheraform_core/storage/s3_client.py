"""Async S3/MinIO client for object storage operations."""

import logging
from pathlib import Path
from typing import Any, AsyncIterator, Optional
from datetime import datetime, timedelta

import aioboto3
from botocore.exceptions import ClientError

from spheraform_core.config import get_settings

logger = logging.getLogger(__name__)


class S3Client:
    """Async S3/MinIO client with connection pooling."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: Optional[str] = None,
        bucket: Optional[str] = None,
    ):
        """
        Initialize S3 client.

        Args:
            endpoint_url: S3 endpoint (for MinIO, e.g., http://localhost:9000)
            access_key: AWS access key ID or MinIO access key
            secret_key: AWS secret access key or MinIO secret key
            region: AWS region (default: us-east-1)
            bucket: Default bucket name
        """
        settings = get_settings()

        self.endpoint_url = endpoint_url or settings.s3_endpoint
        self.public_endpoint_url = settings.s3_public_endpoint or self.endpoint_url
        self.access_key = access_key or settings.s3_access_key
        self.secret_key = secret_key or settings.s3_secret_key
        self.region = region or settings.s3_region
        self.bucket = bucket or settings.s3_bucket

        # Create aioboto3 session
        self.session = aioboto3.Session(
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
        )

    async def _get_client(self):
        """Get async S3 client context manager."""
        return self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
        )

    async def ensure_bucket_exists(self, bucket: Optional[str] = None) -> None:
        """
        Ensure bucket exists, create if it doesn't.

        Args:
            bucket: Bucket name (uses default if not provided)
        """
        bucket = bucket or self.bucket

        async with await self._get_client() as s3:
            try:
                await s3.head_bucket(Bucket=bucket)
                logger.debug(f"Bucket {bucket} exists")
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code")
                if error_code == "404":
                    logger.info(f"Creating bucket {bucket}")
                    await s3.create_bucket(Bucket=bucket)
                else:
                    raise

    async def upload_file(
        self,
        local_path: str | Path,
        s3_key: str,
        bucket: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """
        Upload file to S3/MinIO.

        Args:
            local_path: Local file path
            s3_key: S3 object key (path in bucket)
            bucket: Bucket name (uses default if not provided)
            metadata: Optional metadata dict

        Returns:
            Dict with upload info (bucket, key, size, etag)
        """
        bucket = bucket or self.bucket
        local_path = Path(local_path)

        if not local_path.exists():
            raise FileNotFoundError(f"File not found: {local_path}")

        file_size = local_path.stat().st_size

        async with await self._get_client() as s3:
            logger.info(f"Uploading {local_path} to s3://{bucket}/{s3_key} ({file_size} bytes)")

            extra_args = {}
            if metadata:
                extra_args["Metadata"] = metadata

            with open(local_path, "rb") as f:
                response = await s3.put_object(
                    Bucket=bucket,
                    Key=s3_key,
                    Body=f,
                    **extra_args,
                )

            logger.info(f"Upload complete: {s3_key}")

            return {
                "bucket": bucket,
                "key": s3_key,
                "size": file_size,
                "etag": response.get("ETag", "").strip('"'),
            }

    async def download_file(
        self,
        s3_key: str,
        local_path: str | Path,
        bucket: Optional[str] = None,
    ) -> Path:
        """
        Download file from S3/MinIO.

        Args:
            s3_key: S3 object key (path in bucket)
            local_path: Local destination path
            bucket: Bucket name (uses default if not provided)

        Returns:
            Path to downloaded file
        """
        bucket = bucket or self.bucket
        local_path = Path(local_path)

        # Create parent directory if needed
        local_path.parent.mkdir(parents=True, exist_ok=True)

        async with await self._get_client() as s3:
            logger.info(f"Downloading s3://{bucket}/{s3_key} to {local_path}")

            response = await s3.get_object(Bucket=bucket, Key=s3_key)

            async with response["Body"] as stream:
                with open(local_path, "wb") as f:
                    while chunk := await stream.read(8192):
                        f.write(chunk)

            logger.info(f"Download complete: {local_path}")

        return local_path

    async def delete_object(
        self,
        s3_key: str,
        bucket: Optional[str] = None,
    ) -> None:
        """
        Delete object from S3/MinIO.

        Args:
            s3_key: S3 object key (path in bucket)
            bucket: Bucket name (uses default if not provided)
        """
        bucket = bucket or self.bucket

        async with await self._get_client() as s3:
            logger.info(f"Deleting s3://{bucket}/{s3_key}")
            await s3.delete_object(Bucket=bucket, Key=s3_key)
            logger.info(f"Deleted: {s3_key}")

    async def delete_objects(
        self,
        s3_keys: list[str],
        bucket: Optional[str] = None,
    ) -> None:
        """
        Delete multiple objects from S3/MinIO (batch delete).

        Args:
            s3_keys: List of S3 object keys
            bucket: Bucket name (uses default if not provided)
        """
        if not s3_keys:
            return

        bucket = bucket or self.bucket

        async with await self._get_client() as s3:
            logger.info(f"Deleting {len(s3_keys)} objects from s3://{bucket}/")

            delete_objects = [{"Key": key} for key in s3_keys]

            await s3.delete_objects(
                Bucket=bucket,
                Delete={"Objects": delete_objects},
            )

            logger.info(f"Deleted {len(s3_keys)} objects")

    async def list_objects(
        self,
        prefix: str = "",
        bucket: Optional[str] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        List objects in S3/MinIO with given prefix.

        Args:
            prefix: S3 key prefix to filter by
            bucket: Bucket name (uses default if not provided)

        Yields:
            Dict with object info (key, size, last_modified, etag)
        """
        bucket = bucket or self.bucket

        async with await self._get_client() as s3:
            paginator = s3.get_paginator("list_objects_v2")

            async for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    yield {
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"],
                        "etag": obj.get("ETag", "").strip('"'),
                    }

    async def object_exists(
        self,
        s3_key: str,
        bucket: Optional[str] = None,
    ) -> bool:
        """
        Check if object exists in S3/MinIO.

        Args:
            s3_key: S3 object key
            bucket: Bucket name (uses default if not provided)

        Returns:
            True if object exists, False otherwise
        """
        bucket = bucket or self.bucket

        async with await self._get_client() as s3:
            try:
                await s3.head_object(Bucket=bucket, Key=s3_key)
                return True
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code")
                if error_code == "404":
                    return False
                raise

    async def get_object_metadata(
        self,
        s3_key: str,
        bucket: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Get object metadata from S3/MinIO.

        Args:
            s3_key: S3 object key
            bucket: Bucket name (uses default if not provided)

        Returns:
            Dict with metadata (size, last_modified, content_type, etag, user_metadata)
        """
        bucket = bucket or self.bucket

        async with await self._get_client() as s3:
            response = await s3.head_object(Bucket=bucket, Key=s3_key)

            return {
                "size": response["ContentLength"],
                "last_modified": response["LastModified"],
                "content_type": response.get("ContentType"),
                "etag": response.get("ETag", "").strip('"'),
                "metadata": response.get("Metadata", {}),
            }

    async def get_presigned_url(
        self,
        s3_key: str,
        bucket: Optional[str] = None,
        expiration: int = 3600,
    ) -> str:
        """
        Generate presigned URL for temporary access to object.

        Args:
            s3_key: S3 object key
            bucket: Bucket name (uses default if not provided)
            expiration: URL expiration in seconds (default: 1 hour)

        Returns:
            Presigned URL string
        """
        bucket = bucket or self.bucket

        async with await self._get_client() as s3:
            url = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": s3_key},
                ExpiresIn=expiration,
            )

            return url

    def get_public_url(
        self,
        s3_key: str,
        bucket: Optional[str] = None,
    ) -> str:
        """
        Get public URL for object (without presigning).
        Uses public endpoint if configured, otherwise falls back to internal endpoint.

        Args:
            s3_key: S3 object key
            bucket: Bucket name (uses default if not provided)

        Returns:
            Public URL string (browser-accessible)
        """
        bucket = bucket or self.bucket
        return f"{self.public_endpoint_url}/{bucket}/{s3_key}"
