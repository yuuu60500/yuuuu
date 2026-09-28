"""File storage. The database only stores keys; bytes live here.

LocalStorage is for development. S3Storage works with AWS S3 and Cloudflare R2
(set S3_ENDPOINT_URL to the R2 endpoint).
"""

import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

from .config import get_settings


class Storage(ABC):
    @abstractmethod
    def save(self, key: str, fileobj: BinaryIO) -> int:
        """Store a stream under `key`; returns the number of bytes written."""

    @abstractmethod
    def save_path(self, key: str, path: str) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @contextmanager
    @abstractmethod
    def local_path(self, key: str) -> Iterator[str]:
        """Yield a filesystem path for processing (downloads if remote)."""

    def local_file(self, key: str) -> str | None:
        """Direct path when the backend is local, else None."""
        return None

    def public_url(self, key: str) -> str | None:
        """A URL the browser can stream from, when the backend provides one."""
        return None


class LocalStorage(Storage):
    def __init__(self, base_dir: str):
        self.base = Path(base_dir).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.base / key).resolve()
        if self.base not in path.parents:
            raise ValueError("invalid storage key")
        return path

    def save(self, key: str, fileobj: BinaryIO) -> int:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as out:
            shutil.copyfileobj(fileobj, out, length=1024 * 1024)
        return path.stat().st_size

    def save_path(self, key: str, path: str) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    @contextmanager
    def local_path(self, key: str) -> Iterator[str]:
        yield str(self._path(key))

    def local_file(self, key: str) -> str | None:
        return str(self._path(key))


class S3Storage(Storage):
    def __init__(self, bucket: str, endpoint_url: str | None, region: str | None):
        import boto3  # optional dependency

        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)

    def save(self, key: str, fileobj: BinaryIO) -> int:
        self.client.upload_fileobj(fileobj, self.bucket, key)
        return self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]

    def save_path(self, key: str, path: str) -> None:
        self.client.upload_file(path, self.bucket, key)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    @contextmanager
    def local_path(self, key: str) -> Iterator[str]:
        suffix = os.path.splitext(key)[1]
        fd, tmp = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            self.client.download_file(self.bucket, key, tmp)
            yield tmp
        finally:
            os.remove(tmp)

    def public_url(self, key: str) -> str | None:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=6 * 3600
        )


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        if s.storage_backend == "s3":
            if not s.s3_bucket:
                raise RuntimeError("S3_BUCKET must be set when STORAGE_BACKEND=s3")
            _storage = S3Storage(s.s3_bucket, s.s3_endpoint_url, s.s3_region)
        else:
            _storage = LocalStorage(s.local_storage_dir)
    return _storage
