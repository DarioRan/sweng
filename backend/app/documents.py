"""Manual provenance records (FR-04, US-24): one row per uploaded manual.

Indexing itself (parsing, chunking, embedding) is app.corpus.ingest, reused at request
time by app.corpus.indexer; this module is only the provenance record admins see and
manage, the same split as users.py is to security.py.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    title: str
    source: str
    licence_basis: str
    retrieval_date: str
    pages: int
    status: str  # "indexed" | "error" (app.corpus.indexer)
    detail: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DocumentStore(Protocol):
    async def create(
        self,
        *,
        document_id: str,
        title: str,
        source: str,
        licence_basis: str,
        retrieval_date: str,
        pages: int,
        status: str,
        detail: str | None,
    ) -> DocumentRecord: ...

    async def upsert(
        self,
        *,
        document_id: str,
        title: str,
        source: str,
        licence_basis: str,
        retrieval_date: str,
        pages: int,
        status: str,
        detail: str | None,
    ) -> None:
        """Create the record, or replace it when the manual is indexed again (the CLI)."""
        ...

    async def list_all(self) -> list[DocumentRecord]: ...


# ------------------------------------------------------------- PostgreSQL

metadata = MetaData()

documents_table = Table(
    "documents",
    metadata,
    Column("document_id", String, primary_key=True),
    Column("title", String, nullable=False),
    Column("source", String, nullable=False),
    Column("licence_basis", String, nullable=False),
    Column("retrieval_date", String, nullable=False),
    Column("pages", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("detail", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


class SqlDocumentStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._schema_ready = False
        self._schema_lock = asyncio.Lock()

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        async with self._schema_lock:
            if not self._schema_ready:
                async with self._engine.begin() as conn:
                    await conn.run_sync(metadata.create_all)
                self._schema_ready = True

    @staticmethod
    def _to_record(row) -> DocumentRecord:
        return DocumentRecord(
            document_id=row.document_id,
            title=row.title,
            source=row.source,
            licence_basis=row.licence_basis,
            retrieval_date=row.retrieval_date,
            pages=row.pages,
            status=row.status,
            detail=row.detail,
            created_at=row.created_at.isoformat(),
        )

    async def create(
        self,
        *,
        document_id: str,
        title: str,
        source: str,
        licence_basis: str,
        retrieval_date: str,
        pages: int,
        status: str,
        detail: str | None,
    ) -> DocumentRecord:
        await self._ensure_schema()
        async with self._engine.begin() as conn:
            await conn.execute(
                insert(documents_table).values(
                    document_id=document_id,
                    title=title,
                    source=source,
                    licence_basis=licence_basis,
                    retrieval_date=retrieval_date,
                    pages=pages,
                    status=status,
                    detail=detail,
                )
            )
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    select(documents_table).where(documents_table.c.document_id == document_id)
                )
            ).first()
        return self._to_record(row)  # type: ignore[arg-type]

    async def upsert(
        self,
        *,
        document_id: str,
        title: str,
        source: str,
        licence_basis: str,
        retrieval_date: str,
        pages: int,
        status: str,
        detail: str | None,
    ) -> None:
        await self._ensure_schema()
        values = dict(
            title=title,
            source=source,
            licence_basis=licence_basis,
            retrieval_date=retrieval_date,
            pages=pages,
            status=status,
            detail=detail,
        )
        statement = pg_insert(documents_table).values(document_id=document_id, **values)
        statement = statement.on_conflict_do_update(
            index_elements=[documents_table.c.document_id],
            set_={**values, "created_at": func.now()},
        )
        async with self._engine.begin() as conn:
            await conn.execute(statement)

    async def list_all(self) -> list[DocumentRecord]:
        await self._ensure_schema()
        async with self._engine.connect() as conn:
            rows = (
                await conn.execute(
                    select(documents_table).order_by(documents_table.c.created_at.desc())
                )
            ).all()
        return [self._to_record(r) for r in rows]


# ------------------------------------------------------------- in memory


class InMemoryDocumentStore:
    """For tests."""

    def __init__(self) -> None:
        self._records: dict[str, DocumentRecord] = {}

    async def create(
        self,
        *,
        document_id: str,
        title: str,
        source: str,
        licence_basis: str,
        retrieval_date: str,
        pages: int,
        status: str,
        detail: str | None,
    ) -> DocumentRecord:
        record = DocumentRecord(
            document_id, title, source, licence_basis, retrieval_date, pages, status, detail
        )
        self._records[document_id] = record
        return record

    async def upsert(self, **fields) -> None:  # noqa: ANN003 -- same keywords as create
        await self.create(**fields)

    async def list_all(self) -> list[DocumentRecord]:
        return sorted(self._records.values(), key=lambda d: d.created_at, reverse=True)
