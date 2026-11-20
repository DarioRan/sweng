"""Parse, chunk, embed and index the manual corpus (T-203b).

    docker compose --profile ingest run --rm ingest

Text goes to Qdrant, figures to the figures bucket, and a provenance record per manual
to PostgreSQL, so the admin's manual library lists it. Only manuals recorded in
provenance.csv are indexed (Rule 4). It is safe to rerun: a manual's old chunks and
figures are removed before its new ones are written. It prints one row per manual and
exits non-zero unless every recorded manual is completely indexed and every test
question finds its page.
"""

import argparse
import asyncio
import csv
import io
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium
from fastembed import SparseTextEmbedding, TextEmbedding
from minio import Minio
from pypdf import PdfReader
from qdrant_client import QdrantClient, models
from sqlalchemy.ext.asyncio import create_async_engine
from tokenizers import Tokenizer

from app.config import Settings, get_settings
from app.documents import DocumentStore, SqlDocumentStore
from app.corpus.chunks import body, chunk_page, heading, page_sections, published
from app.corpus.figures import page_figures, page_png
from app.rag.text import part_codes

BATCH = 64
# What the embedder reads. Anything beyond it is cut off silently, so nothing may exceed it.
EMBEDDER_TOKENS = 512
# The heading put in front of each chunk for the embedder is kept to this many characters.
HEADING_CHARS = 200
# How many chunks a search returns. A test question passes when its page is among them.
TOP = 5
# Each chunk is stored twice over: by meaning and by its words. Meaning alone cannot tell
# CS-R9100 from CS-R8000, and a part code is how a repair question names its subject.
DENSE, KEYWORDS = "dense", "bm25"
KEYWORD_MODEL = "Qdrant/bm25"
CANDIDATES = 30  # taken from each of the two searches before they are merged


@dataclass
class CorpusStores:
    """Where the corpus goes, and the embedder that sizes and embeds the chunks."""

    qdrant: QdrantClient
    collection: str
    s3: Minio
    bucket: str
    embedder: TextEmbedding
    keywords: SparseTextEmbedding
    tokens: Callable[[str], int]


@dataclass
class Outcome:
    """What happened to one manual. `status` is 'ok' only when all of it is indexed."""

    manual: str
    status: str
    pages: int = 0
    empty_pages: list[int] = field(default_factory=list)  # page numbers with no text
    chunks: int = 0
    indexed: int = 0
    figures: int = 0
    stored: int = 0
    largest: int = 0  # tokens in the largest chunk as the embedder sees it
    printed: str = ""  # 'YYYY-MM' from the manual's last page


def sections(reader: PdfReader) -> list[str]:
    """For each page, the bookmark it falls under, such as 'INSTALLATION > Brake hose'.

    A page where several sections start names them all. A manual without bookmarks gives ''.
    """
    bookmarks: list[tuple[int, str]] = []

    def walk(items: list, path: tuple[str, ...]) -> None:
        last = path
        for item in items:
            if isinstance(item, list):  # the children of the bookmark just before
                walk(item, last)
                continue
            title = heading(str(item.title))
            last = (*path, title) if title else path
            try:
                page = reader.get_destination_page_number(item)
            except Exception:  # a bookmark that points nowhere is skipped
                continue
            if title and page is not None and page >= 0:
                bookmarks.append((page, " > ".join(last)))

    walk(reader.outline, ())
    return page_sections(bookmarks, len(reader.pages))


def read_pages(pdf: Path) -> tuple[list[str], list[str], str]:
    """Every page's text without its page furniture, every page's section, the print date."""
    reader = PdfReader(pdf)
    if reader.is_encrypted:
        reader.decrypt("")  # many PDFs restrict printing with an empty password
    texts = [body(page.extract_text() or "", n) for n, page in enumerate(reader.pages, start=1)]
    return texts, sections(reader), published(reader.pages[-1].extract_text() or "")


def store_figures(stores: CorpusStores, document_id: str, pdf: Path) -> dict[int, list[str]]:
    """Replace the manual's figures in the bucket. Returns the object keys of each page."""
    stale = stores.s3.list_objects(stores.bucket, prefix=f"{document_id}/", recursive=True)
    for obj in stale:
        stores.s3.remove_object(stores.bucket, obj.object_name)
    keys: dict[int, list[str]] = {}
    document = pdfium.PdfDocument(pdf)
    for number in range(1, len(document) + 1):
        for n, png in enumerate(page_figures(document[number - 1]), start=1):
            key = f"{document_id}/p{number:03d}-{n}.png"
            stores.s3.put_object(
                stores.bucket, key, io.BytesIO(png), len(png), content_type="image/png"
            )
            keys.setdefault(number, []).append(key)
    document.close()
    return keys


def page_key(document_id: str, page: int) -> str:
    """Where a page's render is kept in the figures bucket. /ask shows it to the model."""
    return f"pages/{document_id}/p{page:03d}.png"


def store_pages(stores: CorpusStores, document_id: str, pdf: Path) -> int:
    """Replace the manual's page renders in the bucket. Returns how many the bucket holds.

    The model reads a page as an image as well as text: a table keeps its rows and a
    figure its labels, which text extraction loses (docs/corpus/README.md).
    """
    prefix = f"pages/{document_id}/"
    for obj in stores.s3.list_objects(stores.bucket, prefix=prefix, recursive=True):
        stores.s3.remove_object(stores.bucket, obj.object_name)
    document = pdfium.PdfDocument(pdf)
    for number in range(1, len(document) + 1):
        png = page_png(document[number - 1])
        stores.s3.put_object(
            stores.bucket,
            page_key(document_id, number),
            io.BytesIO(png),
            len(png),
            content_type="image/png",
        )
    document.close()
    return sum(1 for _ in stores.s3.list_objects(stores.bucket, prefix=prefix, recursive=True))


def build_points(
    row: dict[str, str],
    printed: str,
    pages: list[str],
    labels: list[str],
    figures: dict[int, list[str]],
    tokens: Callable[[str], int],
) -> list[dict]:
    """One payload per chunk. The fields are what Citation and Source need (contracts.py).

    `embed` is what the embedder reads: the chunk under a heading that names the manual
    and the section, so a page of bare steps can still be found. It is not stored.
    """
    document_id = f"{row['doc_code']}-{row['revision']}"
    # Every part code the manual names. A page often gives only "B-axle 10 - 12 N·m"; the
    # model it applies to is in the manual's model list. The /ask gate reads this.
    parts = sorted(part_codes("\n".join([row["title"], *labels, *pages])))
    points = []
    for number, (page, section) in enumerate(zip(pages, labels, strict=True), start=1):
        heading = f"{row['title']}\n{section}"[:HEADING_CHARS].strip()
        room = EMBEDDER_TOKENS - tokens(heading)
        for n, text in enumerate(chunk_page(page, room, tokens), start=1):
            points.append(
                {
                    "chunk_id": f"{document_id}:p{number}:c{n}",
                    "document_id": document_id,
                    "document_title": row["title"],
                    "page": number,
                    "section": section,
                    # When two manuals disagree, the answer names the newer one first.
                    "published": printed,
                    "components": row["components"].split("|"),
                    "parts": parts,
                    "figures": figures.get(number, []),
                    "text": text,
                    "is_manufacturer_manual": True,
                    "source_url": row["source_url"],
                    "licence_basis": row["licence_basis"],
                    "retrieval_date": row["retrieval_date"],
                    "embed": f"{heading}\n{text}",
                }
            )
    return points


def of_document(document_id: str) -> models.Filter:
    return models.Filter(
        must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
    )


def sparse_vector(embedding) -> models.SparseVector:
    return models.SparseVector(indices=embedding.indices.tolist(), values=embedding.values.tolist())


def index_manual(stores: CorpusStores, points: list[dict]) -> int:
    """Replace one manual's chunks in the index. Returns how many the index then holds."""
    document = of_document(points[0]["document_id"])
    selector = models.FilterSelector(filter=document)
    stores.qdrant.delete(stores.collection, points_selector=selector, wait=True)
    for i in range(0, len(points), BATCH):
        batch = points[i : i + BATCH]
        texts = [p["embed"] for p in batch]
        vectors = zip(stores.embedder.embed(texts), stores.keywords.embed(texts), strict=True)
        stores.qdrant.upsert(
            stores.collection,
            wait=True,
            points=[
                models.PointStruct(
                    # Derived from the chunk id, so the same chunk always gets the same point.
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, payload["chunk_id"])),
                    vector={DENSE: dense.tolist(), KEYWORDS: sparse_vector(words)},
                    payload={k: v for k, v in payload.items() if k != "embed"},
                )
                for payload, (dense, words) in zip(batch, vectors, strict=True)
            ],
        )
    return stores.qdrant.count(stores.collection, count_filter=document, exact=True).count


def ingest_manual(row: dict[str, str], manuals: Path, stores: CorpusStores) -> Outcome:
    name = f"{row['doc_code']}-{row['revision']}"
    pdf = manuals / row["file_name"]
    if not pdf.is_file():
        return Outcome(name, f"MISSING: {row['file_name']} is not in the manuals folder")
    try:
        pages, labels, printed = read_pages(pdf)
    except Exception as err:  # one damaged PDF is reported in its row, not fatal to the rest
        return Outcome(name, f"UNREADABLE: {type(err).__name__}: {err}")
    figures = store_figures(stores, name, pdf)
    rendered = store_pages(stores, name, pdf)
    points = build_points(row, printed, pages, labels, figures, stores.tokens)
    empty = [number for number, page in enumerate(pages, start=1) if not page]
    result = Outcome(name, "ok", len(pages), empty, len(points), printed=printed)
    result.figures = sum(len(keys) for keys in figures.values())
    in_bucket = stores.s3.list_objects(stores.bucket, prefix=f"{name}/", recursive=True)
    result.stored = sum(1 for _ in in_bucket)
    if not points:
        result.status = "NO TEXT: the PDF has no text layer (a scan needs OCR first)"
        return result
    result.largest = max(stores.tokens(p["embed"]) for p in points)
    result.indexed = index_manual(stores, points)
    if result.indexed != result.chunks:
        result.status = f"INCOMPLETE: the index holds {result.indexed} of {result.chunks} chunks"
    elif rendered != result.pages:
        result.status = f"INCOMPLETE: the bucket holds {rendered} of {result.pages} page renders"
    elif result.stored != result.figures:
        result.status = f"INCOMPLETE: the bucket holds {result.stored} of {result.figures} figures"
    elif not printed:
        result.status = "NO DATE: the print date was not found on the last page"
    elif result.largest > EMBEDDER_TOKENS:
        result.status = f"TOO LONG: a chunk has {result.largest} tokens, the embedder reads 512"
    return result


def ensure_collection(client: QdrantClient, name: str, size: int, recreate: bool) -> None:
    if recreate and client.collection_exists(name):
        client.delete_collection(name)
    if not client.collection_exists(name):
        client.create_collection(
            name,
            vectors_config={DENSE: models.VectorParams(size=size, distance=models.Distance.COSINE)},
            # IDF makes a rare word, such as a part code, count for more than a common one.
            sparse_vectors_config={
                KEYWORDS: models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )
    # Retrieval filters on these: the detected component class, the part named in the
    # question, one manual, and text chunk or figure description. Creating one again is a
    # no-op, so a collection made before a key was added gets it here.
    for key in ("components", "parts", "document_id", "kind"):
        client.create_payload_index(name, key, models.PayloadSchemaType.KEYWORD)
    vectors = client.get_collection(name).config.params.vectors
    held = vectors[DENSE].size if isinstance(vectors, dict) and DENSE in vectors else None
    if held != size:
        sys.exit(
            f"Collection '{name}' does not match: it holds {held}-dimension '{DENSE}' vectors "
            f"and the embedder gives {size}. The embedder or the index layout changed: "
            "rerun with --recreate to rebuild the index."
        )


def search(stores: CorpusStores, question: str) -> list[models.ScoredPoint]:
    """The best text chunks for a question: by meaning and by words, merged by rank.

    Figure descriptions (captions.py) are left out: they are written by a model, and this
    search checks the manuals' own text. /ask has its own search (app/rag/retrieval.py).
    """
    dense = next(iter(stores.embedder.query_embed(question))).tolist()
    words = sparse_vector(next(iter(stores.keywords.query_embed(question))))
    text_only = models.Filter(
        must_not=[models.FieldCondition(key="kind", match=models.MatchValue(value="figure"))]
    )
    found = stores.qdrant.query_points(
        stores.collection,
        prefetch=[
            models.Prefetch(query=dense, using=DENSE, limit=CANDIDATES, filter=text_only),
            models.Prefetch(query=words, using=KEYWORDS, limit=CANDIDATES, filter=text_only),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=TOP,
        with_payload=True,
    )
    return found.points


def check_questions(stores: CorpusStores, path: Path) -> bool:
    """Search for each test question; it passes when its document and page come back."""
    with path.open(newline="", encoding="utf-8") as file:
        questions = list(csv.DictReader(file))
    print(f"\nTest questions ({path.name}): the right page must be in the best {TOP} chunks")
    passed = 0
    for q in questions:
        wanted = (q["document_id"], int(q["page"]))
        hits = [
            (h.payload["document_id"], h.payload["page"]) for h in search(stores, q["question"])
        ]
        ok = wanted in hits
        passed += ok
        where = f"found at rank {hits.index(wanted) + 1}" if ok else f"NOT FOUND, got {hits}"
        print(f"  {'ok  ' if ok else 'FAIL'}  {wanted[0]} p{wanted[1]}  {where}  | {q['question']}")
    print(f"{passed} of {len(questions)} test questions found their page.")
    return passed == len(questions)


def report(outcomes: list[Outcome], stray: list[str], total: int) -> bool:
    """Print one row per manual and the verdict. True when the index is complete."""
    print(
        f"\n{'Manual':<16}{'Pages':>6}{'No text':>9}{'Chunks':>8}{'Indexed':>9}"
        f"{'Figures':>9}{'Tokens':>8}  {'Printed':<8} Status"
    )
    for o in outcomes:
        print(
            f"{o.manual:<16}{o.pages:>6}{len(o.empty_pages):>9}{o.chunks:>8}{o.indexed:>9}"
            f"{o.stored:>9}{o.largest:>8}  {o.printed or '?':<8} {o.status}"
        )
    done = [o for o in outcomes if o.status == "ok"]
    expected = sum(o.chunks for o in done)
    print(f"\n{len(done)} of {len(outcomes)} manuals in provenance.csv are completely indexed.")
    print(f"The index holds {total} chunks; these manuals account for {expected}.")
    print(f"{sum(o.pages for o in done)} pages, {sum(o.stored for o in done)} figures stored.")
    print("Tokens is the largest chunk of each manual as the embedder reads it; the limit is 512.")
    print("\nPages with no text:")
    for o in outcomes:
        if o.empty_pages:
            print(f"  {o.manual}: {', '.join(map(str, o.empty_pages))}")
    if not any(o.empty_pages for o in outcomes):
        print("  none")
    for name in stray:
        print(f"Not indexed, because it is not in provenance.csv: {name}")
    return len(done) == len(outcomes) and total == expected


async def record_manuals(
    store: DocumentStore, results: list[tuple[dict[str, str], Outcome]]
) -> int:
    """Write a provenance record per manual, so the admin's manual library lists it (US-28).

    A manual whose PDF is not in the folder was not indexed and gets no record. Returns
    how many were recorded.
    """
    recorded = 0
    for row, outcome in results:
        if outcome.status.startswith("MISSING"):
            continue
        ok = outcome.status == "ok"
        await store.upsert(
            document_id=outcome.manual,
            title=row["title"],
            source=row["source_url"],
            licence_basis=row["licence_basis"],
            retrieval_date=row["retrieval_date"],
            pages=outcome.pages,
            status="indexed" if ok else "error",
            detail=None if ok else outcome.status,
        )
        recorded += 1
    return recorded


def save_records(settings: Settings, results: list[tuple[dict[str, str], Outcome]]) -> None:
    """record_manuals against PostgreSQL. The index is what matters, so a database that
    cannot be reached is reported and does not fail the run."""
    async def run() -> int:
        engine = create_async_engine(settings.database_url)
        try:
            return await record_manuals(SqlDocumentStore(engine), results)
        finally:
            await engine.dispose()

    try:
        count = asyncio.run(run())
    except Exception as err:  # noqa: BLE001
        print(f"\nWARNING: manuals not recorded in the database ({type(err).__name__}: {err})")
        return
    print(f"\n{count} manual(s) recorded in the admin manual library.")


def connect(settings: Settings, collection: str) -> CorpusStores:
    embedder = TextEmbedding(settings.embedder_model)
    # A copy of the embedder's tokenizer that counts in full. The embedder's own one cuts
    # at the limit, which would hide exactly the over-long chunks this has to catch.
    counter = Tokenizer.from_str(embedder.model.tokenizer.to_str())
    counter.no_truncation()
    counter.no_padding()
    return CorpusStores(
        qdrant=QdrantClient(url=settings.qdrant_url),
        collection=collection,
        s3=Minio(
            settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=settings.s3_secure,
        ),
        bucket=settings.s3_bucket_figures,
        embedder=embedder,
        keywords=SparseTextEmbedding(KEYWORD_MODEL),
        tokens=lambda text: len(counter.encode(text).ids),
    )


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manuals", type=Path, default=Path("/manuals"), help="folder of PDFs")
    parser.add_argument("--provenance", type=Path, default=Path("/corpus/provenance.csv"))
    parser.add_argument("--questions", type=Path, default=Path("/corpus/test_questions.csv"))
    parser.add_argument("--collection", default=settings.qdrant_collection)
    parser.add_argument("--recreate", action="store_true", help="drop the collection first")
    parser.add_argument("--query", help="after indexing, show the best chunks for this")
    args = parser.parse_args()

    with args.provenance.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    stores = connect(settings, args.collection)
    size = len(next(iter(stores.embedder.embed(["size probe"]))))
    ensure_collection(stores.qdrant, args.collection, size, args.recreate)

    outcomes = []
    for row in rows:
        outcome = ingest_manual(row, args.manuals, stores)
        print(f"{outcome.manual}: {outcome.status}", flush=True)
        outcomes.append(outcome)
    save_records(settings, list(zip(rows, outcomes, strict=True)))

    recorded = {row["file_name"] for row in rows}
    stray = sorted(p.name for p in args.manuals.glob("*.pdf") if p.name not in recorded)
    total = stores.qdrant.count(args.collection, exact=True).count
    complete = report(outcomes, stray, total)
    if args.questions.is_file():
        complete = check_questions(stores, args.questions) and complete

    if args.query:
        print(f"\nBest chunks for: {args.query}")
        for hit in search(stores, args.query):
            text = " ".join(hit.payload["text"].split())[:150]
            print(f"  {hit.score:.3f}  {hit.payload['chunk_id']}  {text}")

    sys.exit(0 if complete else 1)


if __name__ == "__main__":
    main()
