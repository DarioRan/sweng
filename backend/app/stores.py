"""Clients for the three stores in §5, plus the probes the health endpoint uses.

PostgreSQL — users, jobs, sessions, provenance
Qdrant     — manual chunks (vector index)
S3         — PDFs, figures, captures (object store; SeaweedFS in the dev stack)
"""

import asyncio
from dataclasses import dataclass

from minio import Minio
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import Settings


@dataclass
class Stores:
    db: AsyncEngine
    qdrant: AsyncQdrantClient
    s3: Minio
    settings: Settings

    @classmethod
    def from_settings(cls, settings: Settings) -> "Stores":
        return cls(
            db=create_async_engine(settings.database_url, pool_pre_ping=True),
            qdrant=AsyncQdrantClient(url=settings.qdrant_url),
            # The MinIO SDK is a plain S3 client; it talks to any S3-compatible store.
            s3=Minio(
                settings.s3_endpoint,
                access_key=settings.s3_access_key,
                secret_key=settings.s3_secret_key,
                secure=settings.s3_secure,
            ),
            settings=settings,
        )

    async def close(self) -> None:
        await self.db.dispose()
        await self.qdrant.close()

    # ------------------------------------------------------------- probes

    async def probe_postgres(self) -> bool:
        async with self.db.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    async def probe_qdrant(self) -> bool:
        await self.qdrant.get_collections()
        return True

    async def probe_s3(self) -> bool:
        # The MinIO SDK is synchronous; keep it off the event loop.
        buckets = [
            self.settings.s3_bucket_manuals,
            self.settings.s3_bucket_figures,
            self.settings.s3_bucket_captures,
        ]
        results = await asyncio.gather(
            *(asyncio.to_thread(self.s3.bucket_exists, b) for b in buckets)
        )
        missing = [b for b, ok in zip(buckets, results, strict=True) if not ok]
        if missing:
            raise RuntimeError(f"missing buckets: {', '.join(missing)}")
        return True

    async def probe_all(self) -> dict[str, dict[str, str]]:
        """Run every probe; report each store as ok or an error string, never raise."""
        probes = {
            "postgres": self.probe_postgres,
            "qdrant": self.probe_qdrant,
            "s3": self.probe_s3,
        }
        outcomes = await asyncio.gather(
            *(p() for p in probes.values()), return_exceptions=True
        )
        report: dict[str, dict[str, str]] = {}
        for name, outcome in zip(probes, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                report[name] = {"status": "error", "detail": f"{type(outcome).__name__}: {outcome}"}
            else:
                report[name] = {"status": "ok"}
        return report
