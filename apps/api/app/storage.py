from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config import Settings
from app.security import create_scoped_signature, verify_scoped_signature


@dataclass(frozen=True)
class UploadGrant:
    provider: str
    storage_path: str
    upload_token: str
    upload_url: str | None
    bucket: str | None
    expires_in_seconds: int


class StorageAdapter(Protocol):
    async def create_upload_grant(self, recording_id: str, storage_path: str) -> UploadGrant: ...

    async def save_local_upload(self, storage_path: str, content: bytes) -> None: ...

    async def read(self, storage_path: str) -> bytes: ...

    async def exists(self, storage_path: str) -> bool: ...

    async def delete(self, storage_path: str) -> None: ...

    async def playback_url(self, recording_id: str, storage_path: str) -> str: ...


class LocalStorageAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.local_storage_path.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, storage_path: str) -> Path:
        resolved = (self.root / storage_path).resolve()
        if self.root not in resolved.parents:
            raise ValueError("Unsafe storage path")
        return resolved

    async def create_upload_grant(self, recording_id: str, storage_path: str) -> UploadGrant:
        signature, expires = create_scoped_signature(
            recording_id, self.settings.upload_signing_secret, 15 * 60
        )
        return UploadGrant(
            provider="local",
            storage_path=storage_path,
            upload_token=f"{expires}.{signature}",
            upload_url=f"{self.settings.public_api_url.rstrip('/')}/v1/uploads/{recording_id}",
            bucket=None,
            expires_in_seconds=15 * 60,
        )

    def verify_upload_token(self, recording_id: str, token: str) -> bool:
        expires_text, separator, signature = token.partition(".")
        if not separator or not expires_text.isdigit():
            return False
        return verify_scoped_signature(
            recording_id,
            signature,
            int(expires_text),
            self.settings.upload_signing_secret,
        )

    async def save_local_upload(self, storage_path: str, content: bytes) -> None:
        path = self._safe_path(storage_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)

    async def read(self, storage_path: str) -> bytes:
        return await asyncio.to_thread(self._safe_path(storage_path).read_bytes)

    async def exists(self, storage_path: str) -> bool:
        return await asyncio.to_thread(self._safe_path(storage_path).is_file)

    async def delete(self, storage_path: str) -> None:
        path = self._safe_path(storage_path)
        if await asyncio.to_thread(path.exists):
            await asyncio.to_thread(path.unlink)

    async def playback_url(self, recording_id: str, storage_path: str) -> str:
        signature, expires = create_scoped_signature(
            recording_id,
            self.settings.upload_signing_secret,
            self.settings.playback_url_ttl_seconds,
        )
        base = self.settings.public_api_url.rstrip("/")
        return f"{base}/v1/playback/{recording_id}?expires={expires}&signature={signature}"


class SupabaseStorageAdapter:
    def __init__(self, settings: Settings) -> None:
        from supabase import create_client

        self.settings = settings
        self.client = create_client(
            settings.supabase_url or "", settings.supabase_service_role_key or ""
        )
        self.bucket = settings.supabase_storage_bucket

    async def create_upload_grant(self, recording_id: str, storage_path: str) -> UploadGrant:
        def create() -> Any:
            return self.client.storage.from_(self.bucket).create_signed_upload_url(storage_path)

        result = await asyncio.to_thread(create)
        data = result if isinstance(result, dict) else getattr(result, "data", result)
        token = data.get("token") if isinstance(data, dict) else None
        if not token:
            raise RuntimeError("Supabase did not return a signed upload token")
        return UploadGrant(
            provider="supabase",
            storage_path=storage_path,
            upload_token=token,
            upload_url=None,
            bucket=self.bucket,
            expires_in_seconds=2 * 60 * 60,
        )

    async def save_local_upload(self, storage_path: str, content: bytes) -> None:
        raise RuntimeError("Direct Supabase uploads must not pass through the API")

    async def read(self, storage_path: str) -> bytes:
        result = await asyncio.to_thread(
            self.client.storage.from_(self.bucket).download, storage_path
        )
        if isinstance(result, bytes):
            return result
        return bytes(result)

    async def exists(self, storage_path: str) -> bool:
        try:
            await self.read(storage_path)
        except Exception:  # noqa: BLE001 - storage SDK has provider-specific exceptions
            return False
        return True

    async def delete(self, storage_path: str) -> None:
        await asyncio.to_thread(self.client.storage.from_(self.bucket).remove, [storage_path])

    async def playback_url(self, recording_id: str, storage_path: str) -> str:
        result = await asyncio.to_thread(
            self.client.storage.from_(self.bucket).create_signed_url,
            storage_path,
            self.settings.playback_url_ttl_seconds,
        )
        data = result if isinstance(result, dict) else getattr(result, "data", result)
        if isinstance(data, dict):
            url = data.get("signedURL") or data.get("signedUrl") or data.get("signed_url")
            if url:
                return str(url)
        raise RuntimeError("Supabase did not return a signed playback URL")


def create_storage(settings: Settings) -> StorageAdapter:
    if settings.storage_mode == "supabase":
        return SupabaseStorageAdapter(settings)
    return LocalStorageAdapter(settings)
