"""Index a manual uploaded through POST /documents (US-24), at request time.

Reuses app.corpus.ingest exactly as the offline `docker compose --profile ingest run`
CLI does (same connect/ensure_collection/ingest_manual), so an uploaded PDF is chunked,
embedded and indexed into Qdrant the same way, with the same figure and page extraction
into the object store. The embedder and the Qdrant client are expensive to build, so one
instance is cached on app.state and reused across uploads (app.rag.service.get_pipeline
does the same for the embedder /ask uses to search).

Tests substitute a fake that implements `index()` without touching Qdrant, S3 or the
embedder — see get_indexer's override in tests/conftest.py.
"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

from fastapi import Request

from app.config import Settings, get_settings
from app.corpus.ingest import Outcome, connect, ensure_collection, ingest_manual

_lock = asyncio.Lock()


class Indexer(Protocol):
    async def index(self, row: dict[str, str], pdf_bytes: bytes, filename: str) -> Outcome: ...


class CorpusIndexer:
    def __init__(self, stores) -> None:  # noqa: ANN001 -- app.corpus.ingest.CorpusStores
        self._stores = stores

    async def index(self, row: dict[str, str], pdf_bytes: bytes, filename: str) -> Outcome:
        def _run() -> Outcome:
            with TemporaryDirectory() as tmp:
                (Path(tmp) / filename).write_bytes(pdf_bytes)
                return ingest_manual(row, Path(tmp), self._stores)

        return await asyncio.to_thread(_run)


def _build(settings: Settings) -> CorpusIndexer:
    stores = connect(settings, settings.qdrant_collection)
    size = len(next(iter(stores.embedder.embed(["size probe"]))))
    ensure_collection(stores.qdrant, settings.qdrant_collection, size, recreate=False)
    return CorpusIndexer(stores)


async def get_indexer(request: Request) -> Indexer:
    indexer = getattr(request.app.state, "corpus_indexer", None)
    if indexer is None:
        async with _lock:
            indexer = getattr(request.app.state, "corpus_indexer", None)
            if indexer is None:
                settings = get_settings()
                indexer = await asyncio.to_thread(_build, settings)
                request.app.state.corpus_indexer = indexer
    return indexer
