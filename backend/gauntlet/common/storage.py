"""Artefact storage: two-channel call WAVs and waveform peak files (SRS 7 K).

S3-compatible object storage when configured (private bucket, pre-signed URLs valid for 300 s,
SRS-SEC-015); otherwise the local disk under .data/artifacts, served through authenticated endpoints.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from gauntlet.common.paths import DATA_DIR


class Storage:
    def __init__(self, bucket: str = "", endpoint_url: str = "", access_key: str = "", secret_key: str = "",
                 root: Path | None = None):
        self.bucket = bucket
        self.root = root or DATA_DIR / "artifacts"
        self._s3 = None
        if bucket:
            import boto3  # optional dependency: backend[storage]

            self._s3 = boto3.client("s3", endpoint_url=endpoint_url or None, aws_access_key_id=access_key or None,
                                    aws_secret_access_key=secret_key or None, region_name="auto")
        else:
            self.root.mkdir(parents=True, exist_ok=True)

    @property
    def kind(self) -> str:
        return "s3" if self._s3 else "local"

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        for attempt in range(3):
            try:
                if self._s3:
                    await asyncio.to_thread(self._s3.put_object, Bucket=self.bucket, Key=key, Body=data,
                                            ContentType=content_type)
                    return f"s3://{self.bucket}/{key}"
                p = self.root / key
                p.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(p.write_bytes, data)
                return f"local://{key}"
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.25 * (2**attempt))
        raise RuntimeError("unreachable")

    async def get(self, uri: str) -> bytes | None:
        try:
            if uri.startswith("s3://") and self._s3:
                key = uri.split("/", 3)[3]
                obj = await asyncio.to_thread(self._s3.get_object, Bucket=self.bucket, Key=key)
                return obj["Body"].read()
            if uri.startswith("local://"):
                p = self.root / uri[len("local://"):]
                return await asyncio.to_thread(p.read_bytes) if p.exists() else None
        except Exception:
            return None
        return None

    def presign(self, uri: str, seconds: int = 300) -> str | None:
        if uri.startswith("s3://") and self._s3:
            key = uri.split("/", 3)[3]
            return self._s3.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key},
                                                   ExpiresIn=seconds)
        return None

    async def delete(self, uri: str) -> None:
        try:
            if uri.startswith("s3://") and self._s3:
                await asyncio.to_thread(self._s3.delete_object, Bucket=self.bucket, Key=uri.split("/", 3)[3])
            elif uri.startswith("local://"):
                p = self.root / uri[len("local://"):]
                if p.exists():
                    p.unlink()
        except Exception:
            pass
