"""Abstract storage backend interface."""

from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    @abstractmethod
    async def write_file(self, key: str, data: bytes) -> str:
        """Write file from bytes. Returns the storage key."""

    @abstractmethod
    async def write_from_path(self, key: str, local_path: Path) -> str:
        """Upload a local file to storage. Returns the storage key."""

    @abstractmethod
    async def read_file(self, key: str) -> bytes:
        """Read file contents as bytes."""

    async def read_header(self, key: str, size: int = 12) -> bytes:
        """Read only the first N bytes of a file. Default: full read + slice."""
        data = await self.read_file(key)
        return data[:size]

    @abstractmethod
    async def get_url(self, key: str, expires: int = 3600, force_download: bool = False) -> str:
        """Get a URL for the file. Pre-signed for S3, local path for disk.

        If force_download=True, the URL will include Content-Disposition: attachment
        to prevent the browser from rendering the file inline.
        """

    @abstractmethod
    async def delete_file(self, key: str) -> None:
        """Delete a file from storage."""

    @abstractmethod
    async def file_exists(self, key: str) -> bool:
        """Check if file exists in storage."""

    @abstractmethod
    async def delete_prefix(self, prefix: str) -> int:
        """Delete all keys matching a prefix. Returns count of deleted keys."""

    @abstractmethod
    async def list_prefixes(self, prefix: str, delimiter: str = "/") -> list[str]:
        """List unique sub-prefixes under a prefix (like S3 CommonPrefixes).

        E.g. list_prefixes("frames/", "/") → ["frames/uuid1/", "frames/uuid2/"]
        """

    @abstractmethod
    async def find_keys(self, prefix: str, limit: int = 10) -> list[str]:
        """List keys matching a prefix."""

    async def download_to_path(self, key: str, local_path: Path) -> None:
        """Download a file from storage to local disk (streaming, memory-safe).

        Default implementation uses read_file (loads into memory).
        S3 backend overrides with streaming download.
        """
        data = await self.read_file(key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)

    async def get_upload_url(self, key: str, expires: int = 3600, content_type: str | None = None) -> str:
        """Get a pre-signed URL for uploading (PUT). S3-only."""
        raise NotImplementedError("Upload URLs not supported by this storage backend")
