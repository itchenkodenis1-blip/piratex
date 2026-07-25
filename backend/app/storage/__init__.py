"""Storage layer — abstracts local disk vs S3/R2."""

from app.config import settings
from app.storage.base import StorageBackend


def get_storage() -> StorageBackend:
    """Return the configured storage backend (S3 if configured, else local disk)."""
    if settings.s3_bucket:
        from app.storage.s3 import S3Storage
        return S3Storage()
    from app.storage.local import LocalStorage
    return LocalStorage()


# Singleton instance — import this everywhere
storage = get_storage()
