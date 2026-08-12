"""Local disk storage backend + legacy helper functions."""

import shutil
from pathlib import Path

from app.config import settings
from app.storage.base import StorageBackend


# ---------------------------------------------------------------------------
# StorageBackend implementation
# ---------------------------------------------------------------------------

class LocalStorage(StorageBackend):
    def __init__(self):
        self._root = Path(settings.storage_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise ValueError("Invalid storage key")
        return path

    async def write_file(self, key: str, data: bytes) -> str:
        path = self._safe_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    async def write_from_path(self, key: str, local_path: Path) -> str:
        dest = self._safe_path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if local_path.resolve() != dest.resolve():
            shutil.copy2(str(local_path), str(dest))
        return key

    async def read_file(self, key: str) -> bytes:
        path = self._safe_path(key)
        return path.read_bytes()

    async def get_url(self, key: str, expires: int = 3600, force_download: bool = False) -> str:
        url = f"/api/files/{key}"
        if force_download:
            url += "?download=1"
        return url

    async def delete_file(self, key: str) -> None:
        path = self._safe_path(key)
        if path.is_file():
            path.unlink()

    async def delete_prefix(self, prefix: str) -> int:
        target = self._safe_path(prefix)
        deleted = 0
        if target.is_dir():
            for f in target.rglob("*"):
                if f.is_file():
                    f.unlink()
                    deleted += 1
            shutil.rmtree(target, ignore_errors=True)
        else:
            directory = target.parent
            pattern = target.name + "*"
            if directory.is_dir():
                for p in directory.glob(pattern):
                    if p.is_file():
                        p.unlink()
                        deleted += 1
        return deleted

    async def file_exists(self, key: str) -> bool:
        return self._safe_path(key).is_file()

    async def list_prefixes(self, prefix: str, delimiter: str = "/") -> list[str]:
        target = self._safe_path(prefix)
        if not target.is_dir():
            return []
        return [
            str(d.relative_to(self._root)) + delimiter
            for d in sorted(target.iterdir())
            if d.is_dir()
        ]

    async def find_keys(self, prefix: str, limit: int = 10) -> list[str]:
        parent = self._safe_path(prefix)
        directory = parent.parent
        pattern = parent.name + "*"
        if not directory.is_dir():
            return []
        return [
            str(p.relative_to(self._root))
            for p in sorted(directory.glob(pattern))[:limit]
        ]

    async def download_to_path(self, key: str, local_path: Path) -> None:
        """Copy file from local storage to another local path."""
        src = self._safe_path(key)
        if src.resolve() != local_path.resolve():
            local_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(local_path))

    def get_local_path(self, key: str) -> Path:
        """Get the local filesystem path for a key. LocalStorage only."""
        return self._safe_path(key)


# ---------------------------------------------------------------------------
# Legacy helpers (used by existing code, gradually migrate to StorageBackend)
# ---------------------------------------------------------------------------

def get_storage_dir() -> Path:
    path = Path(settings.storage_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_videos_dir() -> Path:
    path = get_storage_dir() / "videos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_audio_dir() -> Path:
    path = get_storage_dir() / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_frames_dir(job_id: str) -> Path:
    path = get_storage_dir() / "frames" / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path
