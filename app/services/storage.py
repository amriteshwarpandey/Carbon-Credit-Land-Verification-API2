"""File storage for certificates and evidence: local directory or any S3-compatible object store.

Callers deal only in opaque keys such as ``certificates/certificate_7.pdf``; the backend decides where
bytes live, so API and Celery workers on different hosts can share files by using the "s3" backend.
"""
from pathlib import Path
from typing import Protocol

from app.config import settings


class StorageError(Exception):
    pass


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        if Path(key).is_absolute():  # legacy rows stored absolute paths
            return Path(key)
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise StorageError("Invalid storage key")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise StorageError(f"File not found: {key}") from exc


class S3Storage:
    def __init__(self):
        if not settings.s3_bucket:
            raise StorageError("S3_BUCKET must be set when STORAGE_BACKEND=s3")
        import boto3  # lazy: only needed for the s3 backend

        self.bucket = settings.s3_bucket
        self.prefix = settings.s3_prefix.strip("/")
        self.client = boto3.client("s3", endpoint_url=settings.s3_endpoint_url, region_name=settings.s3_region)

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()
        except self.client.exceptions.NoSuchKey as exc:
            raise StorageError(f"File not found: {key}") from exc


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = S3Storage() if settings.storage_backend == "s3" else LocalStorage(settings.certificates_dir)
    return _storage
