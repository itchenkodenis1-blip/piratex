"""S3-compatible storage backend (AWS S3, Railway Buckets, Cloudflare R2, MinIO)."""

import asyncio
import logging
from pathlib import Path

import aioboto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import settings
from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class S3Storage(StorageBackend):
    def __init__(self):
        self.bucket = settings.s3_bucket
        self.session = aioboto3.Session(
            aws_access_key_id=settings.s3_access_key or None,
            aws_secret_access_key=settings.s3_secret_key or None,
            region_name=settings.s3_region or None,
        )
        self._endpoint = settings.s3_endpoint or None
        self._cdn_url = settings.cdn_url or None

    def _client_kwargs(self) -> dict:
        kw: dict = {}
        if self._endpoint:
            kw["endpoint_url"] = self._endpoint
            # Auto-detect addressing style based on provider
            style = settings.s3_addressing_style
            if not style:
                # Railway Buckets use storageapi.dev or storage.railway.app
                is_railway = any(
                    d in self._endpoint
                    for d in ("railway", "storageapi.dev")
                )
                style = "virtual" if is_railway else "path"
            kw["config"] = BotoConfig(s3={"addressing_style": style})
        return kw

    async def _retry_s3(self, operation, max_retries: int = 3):
        """Retry S3 operation with exponential backoff on transient errors."""
        for attempt in range(max_retries):
            try:
                return await operation()
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("RequestCanceled", "RequestTimeout", "SlowDown") and attempt < max_retries - 1:
                    delay = 2 ** attempt
                    logger.warning(
                        "S3 %s (attempt %d/%d), retrying in %ds...",
                        code, attempt + 1, max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

    async def write_file(self, key: str, data: bytes) -> str:
        async def _op():
            async with self.session.client("s3", **self._client_kwargs()) as s3:
                await s3.put_object(Bucket=self.bucket, Key=key, Body=data)
        await self._retry_s3(_op)
        return key

    async def write_from_path(self, key: str, local_path: Path) -> str:
        async def _op():
            async with self.session.client("s3", **self._client_kwargs()) as s3:
                await s3.upload_file(str(local_path), self.bucket, key)
        await self._retry_s3(_op)
        return key

    async def read_file(self, key: str) -> bytes:
        async with self.session.client("s3", **self._client_kwargs()) as s3:
            resp = await s3.get_object(Bucket=self.bucket, Key=key)
            return await resp["Body"].read()

    async def read_header(self, key: str, size: int = 12) -> bytes:
        """Read only the first N bytes of a file (range request)."""
        async with self.session.client("s3", **self._client_kwargs()) as s3:
            resp = await s3.get_object(
                Bucket=self.bucket, Key=key, Range=f"bytes=0-{size - 1}",
            )
            return await resp["Body"].read()

    async def get_url(self, key: str, expires: int = 3600, force_download: bool = False) -> str:
        # If CDN URL is configured and no special headers needed, use it directly
        if self._cdn_url and not force_download:
            return f"{self._cdn_url.rstrip('/')}/{key}"

        # Otherwise generate pre-signed URL
        params: dict = {"Bucket": self.bucket, "Key": key}
        if force_download:
            filename = key.rsplit("/", 1)[-1] if "/" in key else key
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
            params["ResponseContentType"] = "application/octet-stream"
        async with self.session.client("s3", **self._client_kwargs()) as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expires,
            )

    async def delete_file(self, key: str) -> None:
        async with self.session.client("s3", **self._client_kwargs()) as s3:
            await s3.delete_object(Bucket=self.bucket, Key=key)

    async def delete_prefix(self, prefix: str) -> int:
        deleted = 0
        async with self.session.client("s3", **self._client_kwargs()) as s3:
            continuation_token = None
            while True:
                kwargs = {"Bucket": self.bucket, "Prefix": prefix, "MaxKeys": 1000}
                if continuation_token:
                    kwargs["ContinuationToken"] = continuation_token
                resp = await s3.list_objects_v2(**kwargs)
                objects = resp.get("Contents", [])
                if not objects:
                    break
                await s3.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
                )
                deleted += len(objects)
                if not resp.get("IsTruncated"):
                    break
                continuation_token = resp.get("NextContinuationToken")
        return deleted

    async def file_exists(self, key: str) -> bool:
        try:
            async with self.session.client("s3", **self._client_kwargs()) as s3:
                await s3.head_object(Bucket=self.bucket, Key=key)
                return True
        except Exception:
            return False

    async def list_prefixes(self, prefix: str, delimiter: str = "/") -> list[str]:
        prefixes: list[str] = []
        async with self.session.client("s3", **self._client_kwargs()) as s3:
            continuation_token = None
            while True:
                kwargs = {
                    "Bucket": self.bucket,
                    "Prefix": prefix,
                    "Delimiter": delimiter,
                    "MaxKeys": 1000,
                }
                if continuation_token:
                    kwargs["ContinuationToken"] = continuation_token
                resp = await s3.list_objects_v2(**kwargs)
                for cp in resp.get("CommonPrefixes", []):
                    prefixes.append(cp["Prefix"])
                if not resp.get("IsTruncated"):
                    break
                continuation_token = resp.get("NextContinuationToken")
        return prefixes

    async def find_keys(self, prefix: str, limit: int = 10) -> list[str]:
        async with self.session.client("s3", **self._client_kwargs()) as s3:
            resp = await s3.list_objects_v2(
                Bucket=self.bucket, Prefix=prefix, MaxKeys=limit,
            )
            return [obj["Key"] for obj in resp.get("Contents", [])]

    async def download_to_path(self, key: str, local_path: Path) -> None:
        """Stream file from S3 to local disk without loading into memory."""
        local_path.parent.mkdir(parents=True, exist_ok=True)
        async with self.session.client("s3", **self._client_kwargs()) as s3:
            await s3.download_file(self.bucket, key, str(local_path))

    async def get_upload_url(self, key: str, expires: int = 3600, content_type: str | None = None) -> str:
        """Generate a pre-signed PUT URL for direct browser upload."""
        params: dict = {"Bucket": self.bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        async with self.session.client("s3", **self._client_kwargs()) as s3:
            return await s3.generate_presigned_url(
                "put_object",
                Params=params,
                ExpiresIn=expires,
            )
