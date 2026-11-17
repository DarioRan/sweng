"""Make the figures searchable: describe each one with the vision model, index the description.

    docker compose --profile ingest --profile local run --rm ingest python -m app.corpus.captions

Run it after `app.corpus.ingest`, which crops the figures. The manuals' figures have no
caption, only part labels, so a question such as "show the exploded view of the cassette"
has nothing to find. The vision model writes one or two sentences for each figure, and the
sentence is indexed beside the text as a point of kind 'figure'.

A description is written by a model, not by Shimano, so it is never shown as evidence:
a search that finds it is sent on to the manual's own text of the same page
(app/rag/retrieval.py). It only decides which page, and which figure, is found.

Descriptions are kept in a cache file per model, so rerunning after a new ingest
re-indexes them without asking the model again.
"""

import argparse
import base64
import json
import sys
import time
import uuid
from pathlib import Path

import httpx
from qdrant_client import models

from app.config import get_settings
from app.corpus.ingest import DENSE, KEYWORDS, connect, sparse_vector

PROMPT = """\
This figure is from page {page} of the Shimano dealer's manual "{title}", section \
"{section}". In one or two sentences, say which part or parts it shows and what is being \
done (for example: an exploded view, a tool turning a bolt, a measurement). Name only what \
is visible. Do not give any value, torque or size."""

BATCH = 32


def describe(url: str, model: str, png: bytes, prompt: str) -> str:
    reply = httpx.post(
        f"{url}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "user", "content": prompt, "images": [base64.b64encode(png).decode()]}
            ],
            "options": {"temperature": 0, "seed": 0, "num_predict": 120, "num_ctx": 4096},
            "think": False,
            "stream": False,
        },
        timeout=300,
    )
    reply.raise_for_status()
    return " ".join(reply.json()["message"]["content"].split())


def text_pages(stores) -> dict[tuple[str, int], dict]:
    """The first text chunk's payload of every page, keyed by (document, page)."""
    pages: dict[tuple[str, int], dict] = {}
    offset = None
    while True:
        points, offset = stores.qdrant.scroll(
            stores.collection,
            scroll_filter=models.Filter(
                must_not=[
                    models.FieldCondition(key="kind", match=models.MatchValue(value="figure"))
                ]
            ),
            limit=256,
            offset=offset,
            with_payload=True,
        )
        for point in points:
            p = point.payload or {}
            pages.setdefault((p["document_id"], p["page"]), p)
        if offset is None:
            return pages


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=settings.llm_local_model)
    parser.add_argument("--cache", type=Path, default=Path("/models/captions"))
    parser.add_argument("--limit", type=int, default=0, help="describe at most this many (a trial)")
    args = parser.parse_args()

    stores = connect(settings, settings.qdrant_collection)
    url = settings.llm_local_url.rstrip("/")
    cache_file = args.cache / f"{args.model.replace(':', '_').replace('/', '_')}.json"
    cache: dict[str, str] = json.loads(cache_file.read_text()) if cache_file.is_file() else {}
    args.cache.mkdir(parents=True, exist_ok=True)

    pages = text_pages(stores)
    figures = [(key, page) for page in pages.values() for key in page.get("figures", [])]
    if args.limit:
        figures = figures[: args.limit]
    print(f"{len(figures)} figures on {len(pages)} pages; {len(cache)} already described.")

    started, asked = time.monotonic(), 0
    for n, (key, page) in enumerate(figures, start=1):
        if key in cache:
            continue
        png = stores.s3.get_object(stores.bucket, key).read()
        prompt = PROMPT.format(
            page=page["page"], title=page["document_title"], section=page.get("section") or "-"
        )
        cache[key] = describe(url, args.model, png, prompt)
        asked += 1
        if asked % 25 == 0:
            cache_file.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
            rate = asked / (time.monotonic() - started)
            print(
                f"  {n}/{len(figures)}  {rate:.1f} figures/s  {key}: {cache[key][:80]}", flush=True
            )
    cache_file.write_text(json.dumps(cache, indent=1, ensure_ascii=False))

    # Replace every figure point with the current descriptions.
    stores.qdrant.delete(
        stores.collection,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[models.FieldCondition(key="kind", match=models.MatchValue(value="figure"))]
            )
        ),
        wait=True,
    )
    payloads = []
    for key, page in figures:
        heading = f"{page['document_title']}\n{page.get('section', '')}"
        payloads.append(
            {
                "kind": "figure",
                "chunk_id": f"{key}:figure",
                "figure": key,
                "document_id": page["document_id"],
                "document_title": page["document_title"],
                "page": page["page"],
                "section": page.get("section", ""),
                "published": page.get("published", ""),
                "components": page.get("components", []),
                "parts": page.get("parts", []),
                "text": cache[key],
                "embed": f"{heading}\nFigure: {cache[key]}",
            }
        )
    for i in range(0, len(payloads), BATCH):
        batch = payloads[i : i + BATCH]
        texts = [p.pop("embed") for p in batch]
        vectors = zip(stores.embedder.embed(texts), stores.keywords.embed(texts), strict=True)
        stores.qdrant.upsert(
            stores.collection,
            wait=True,
            points=[
                models.PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, p["chunk_id"])),
                    vector={DENSE: dense.tolist(), KEYWORDS: sparse_vector(words)},
                    payload=p,
                )
                for p, (dense, words) in zip(batch, vectors, strict=True)
            ],
        )
    held = stores.qdrant.count(
        stores.collection,
        count_filter=models.Filter(
            must=[models.FieldCondition(key="kind", match=models.MatchValue(value="figure"))]
        ),
        exact=True,
    ).count
    print(f"The index holds {held} figure descriptions of {len(figures)} figures.")
    sys.exit(0 if held == len(figures) else 1)


if __name__ == "__main__":
    main()
