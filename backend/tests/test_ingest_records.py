"""The ingest CLI records each manual it indexed, so the admin manual library lists it.

Plain functions running asyncio.run: CI has no async pytest plugin.
"""

import asyncio

from app.corpus.ingest import Outcome, record_manuals
from app.documents import InMemoryDocumentStore


def _row(code: str, title: str) -> dict[str, str]:
    return {
        "doc_code": code,
        "revision": "06",
        "file_name": f"{code}-06-ENG.pdf",
        "title": title,
        "components": "crankset",
        "source_url": f"https://example.com/{code}.pdf",
        "licence_basis": "shimano-tou-private",
        "retrieval_date": "2026-10-05",
    }


def test_records_indexed_and_failed_manuals_but_not_missing_ones():
    store = InMemoryDocumentStore()
    results = [
        (_row("DM-A", "Crankset"), Outcome("DM-A-06", "ok", pages=40)),
        (_row("DM-B", "Chain"), Outcome("DM-B-06", "NO DATE: not found", pages=12)),
        (_row("DM-C", "Brake"), Outcome("DM-C-06", "MISSING: not in the folder")),
    ]

    assert asyncio.run(record_manuals(store, results)) == 2

    records = {r.document_id: r for r in asyncio.run(store.list_all())}
    assert set(records) == {"DM-A-06", "DM-B-06"}
    assert records["DM-A-06"].status == "indexed"
    assert records["DM-A-06"].pages == 40
    assert records["DM-A-06"].title == "Crankset"
    assert records["DM-A-06"].source == "https://example.com/DM-A.pdf"
    assert records["DM-B-06"].status == "error"
    assert records["DM-B-06"].detail == "NO DATE: not found"


def test_rerunning_replaces_the_record():
    store = InMemoryDocumentStore()
    failed = Outcome("DM-A-06", "UNREADABLE: x")
    asyncio.run(record_manuals(store, [(_row("DM-A", "Crankset"), failed)]))
    indexed = Outcome("DM-A-06", "ok", pages=40)
    asyncio.run(record_manuals(store, [(_row("DM-A", "Crankset"), indexed)]))

    [record] = asyncio.run(store.list_all())
    assert record.status == "indexed"
    assert record.pages == 40
