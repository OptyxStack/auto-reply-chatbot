"""Object storage for raw docs, parsed docs, artifacts (S3/MinIO compatible)."""

from typing import BinaryIO

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ObjectStorage:
    """S3/MinIO compatible object storage."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None

    def _get_client(self):
        if self._client is None and self._settings.object_storage_url:
            try:
                import boto3
                from botocore.config import Config
                self._client = boto3.client(
                    "s3",
                    endpoint_url=self._settings.object_storage_url,
                    aws_access_key_id=self._settings.object_storage_access_key,
                    aws_secret_access_key=self._settings.object_storage_secret_key,
                    config=Config(signature_version="s3v4"),
                )
            except ImportError:
                logger.warning("boto3 not installed, object storage disabled")
        return self._client

    def put(self, key: str, body: bytes | BinaryIO, content_type: str = "application/octet-stream") -> bool:
        """Upload object. Returns True on success."""
        client = self._get_client()
        if not client:
            return False
        try:
            client.put_object(
                Bucket=self._settings.object_storage_bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
            return True
        except Exception as e:
            logger.error("storage_put_failed", key=key, error=str(e))
            return False

    def get(self, key: str) -> bytes | None:
        """Download object. Returns None if not found."""
        client = self._get_client()
        if not client:
            return None
        try:
            resp = client.get_object(Bucket=self._settings.object_storage_bucket, Key=key)
            return resp["Body"].read()
        except client.exceptions.NoSuchKey:
            return None
        except Exception as e:
            logger.error("storage_get_failed", key=key, error=str(e))
            return None

    def exists(self, key: str) -> bool:
        """Check if object exists."""
        client = self._get_client()
        if not client:
            return False
        try:
            client.head_object(Bucket=self._settings.object_storage_bucket, Key=key)
            return True
        except Exception:
            return False


def get_storage() -> ObjectStorage:
    return ObjectStorage()
