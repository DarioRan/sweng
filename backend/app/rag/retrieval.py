"""Find the passages for a question, and score how well each one answers it.

1. **Scope.** A part code in the question (BR-R9270) limits the search to the manuals
   that name that part, and the detected component class to the manuals that cover it.
2. **Search.** The hybrid search of ingestion: meaning and keywords, merged by rank.
3. **Score.** Each candidate gets a score for how well it matches the question: by
   default the embedder's own similarity between the question and the passage (`dense`),
   read from the vectors the index already holds. The merged rank of the search says only
   which candidate is better, never whether any is good enough, so the abstention
   threshold (gate.py) is set on this score. A cross-encoder can be named instead; five
   were measured and none separated answerable from unanswerable questions better
   (app.rag.calibrate, ADR 0004).
4. **Select.** The five best, in the search's order. The scorer's order and adding the
   neighbouring pages of the best passage were measured too and reached no more answers,
   so both are off by default.

A figure point (captions.py) is a model-written description of a figure. It is used only
to find a page: it is swapped for the manual's own text of that page, and never reaches
the model or the user as evidence.
"""

import math
from dataclasses import dataclass, field

import numpy as np
from fastembed import SparseTextEmbedding, TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from qdrant_client import QdrantClient, models

from app.corpus.ingest import CANDIDATES, DENSE, KEYWORD_MODEL, KEYWORDS, sparse_vector
from app.rag.text import part_codes

# Candidates scored, and passages kept.
RERANK = 20
KEEP = 5
# The default scorer: the embedder's own similarity, read from the index. Any other name
# is a fastembed cross-encoder, such as 'Xenova/ms-marco-MiniLM-L-6-v2'.
DENSE_SCORER = "dense"


@dataclass
class Passage:
    chunk_id: str
    document_id: str
    document_title: str
    page: int
    section: str
    published: str  # 'YYYY-MM'
    text: str
    figures: list[str] = field(default_factory=list)  # object keys in the figures bucket
    parts: list[str] = field(default_factory=list)  # every part code its manual names
    is_manufacturer_manual: bool = True
    score: float = 0.0  # the cross-encoder's, as a probability (0-1)
    found_by_figure: str | None = None  # the figure whose description found this page
    vector: list[float] | None = field(default=None, repr=False)  # its dense embedding

    @classmethod
    def from_point(cls, point) -> "Passage":
        passage = cls.from_payload(point.payload or {})
        vectors = point.vector if isinstance(point.vector, dict) else {}
        passage.vector = vectors.get(DENSE)
        return passage

    @classmethod
    def from_payload(cls, payload: dict) -> "Passage":
        return cls(
            chunk_id=payload["chunk_id"],
            document_id=payload["document_id"],
            document_title=payload["document_title"],
            page=payload["page"],
            section=payload.get("section", ""),
            published=payload.get("published", ""),
            text=payload["text"],
            figures=list(payload.get("figures", [])),
            parts=list(payload.get("parts", [])),
            is_manufacturer_manual=payload.get("is_manufacturer_manual", True),
        )


def sigmoid(logit: float) -> float:
    return 1 / (1 + math.exp(-logit))


def with_heading(passage: Passage) -> str:
    """What the cross-encoder reads: the passage under its manual and section."""
    return f"{passage.document_title}\n{passage.section}\n{passage.text}"


class Retriever:
    def __init__(
        self,
        qdrant: QdrantClient,
        collection: str,
        embedder_model: str,
        scorer: str = DENSE_SCORER,
        cache_dir: str | None = None,
        order: str = "hybrid",
        neighbours: bool = False,
    ) -> None:
        self.qdrant = qdrant
        self.collection = collection
        self.embedder = TextEmbedding(embedder_model, cache_dir=cache_dir)
        self.keywords = SparseTextEmbedding(KEYWORD_MODEL, cache_dir=cache_dir)
        self.reranker = (
            None if scorer == DENSE_SCORER else TextCrossEncoder(scorer, cache_dir=cache_dir)
        )
        self.order = order  # 'hybrid': the search's order; 'rerank': the scorer's
        self.neighbours = neighbours

    # ------------------------------------------------------------------ search
    def candidates(self, question: str, component: str | None = None) -> list[Passage]:
        """The hybrid search's candidates, best first: text chunks, and the pages of the
        figures whose description matched. Scoped to the part and the component."""
        must = []
        if component:  # the detected class: only the manuals that cover it
            must.append(
                models.FieldCondition(key="components", match=models.MatchAny(any=[component]))
            )
        # The parts named: only the manuals that name every one of them. "Where does
        # TL-SR24 go on a CS-M9100?" is for the manual of that cassette, not for every
        # manual that uses the tool.
        for code in sorted(part_codes(question)):
            must.append(models.FieldCondition(key="parts", match=models.MatchValue(value=code)))
        where = models.Filter(must=must) if must else None
        dense = next(iter(self.embedder.query_embed(question))).tolist()
        words = sparse_vector(next(iter(self.keywords.query_embed(question))))
        found = self.qdrant.query_points(
            self.collection,
            prefetch=[
                models.Prefetch(query=dense, using=DENSE, limit=CANDIDATES, filter=where),
                models.Prefetch(query=words, using=KEYWORDS, limit=CANDIDATES, filter=where),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=RERANK,
            with_payload=True,
            with_vectors=[DENSE],
        ).points
        passages: dict[str, Passage] = {}
        for hit in found:
            payload = hit.payload or {}
            if payload.get("kind") == "figure":
                for passage in self.page_text(payload["document_id"], payload["page"]):
                    passage.found_by_figure = payload["figure"]
                    passages.setdefault(passage.chunk_id, passage)
            else:
                passages.setdefault(payload["chunk_id"], Passage.from_point(hit))
        return list(passages.values())

    def page_text(self, document_id: str, page: int) -> list[Passage]:
        """The manual's own text chunks of one page."""
        points, _ = self.qdrant.scroll(
            self.collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=document_id)
                    ),
                    models.FieldCondition(key="page", match=models.MatchValue(value=page)),
                ],
                must_not=[
                    models.FieldCondition(key="kind", match=models.MatchValue(value="figure"))
                ],
            ),
            limit=10,
            with_payload=True,
            with_vectors=[DENSE],
        )
        return [Passage.from_point(p) for p in points]

    # ------------------------------------------------------------------- score
    def score(self, question: str, passages: list[Passage]) -> list[Passage]:
        """Give every passage its score against the question (0-1). The order is kept."""
        if not passages:
            return passages
        if self.reranker is None:
            # Cosine similarity: the embedder and the index both keep unit vectors.
            query = next(iter(self.embedder.query_embed(question)))
            scores = [max(0.0, float(query @ np.asarray(p.vector))) for p in passages]
        else:
            texts = [with_heading(p) for p in passages]
            scores = [sigmoid(float(logit)) for logit in self.reranker.rerank(question, texts)]
        for passage, value in zip(passages, scores, strict=True):
            passage.score = value
        return passages

    def select(self, scored: list[Passage], keep: int = KEEP, order: str | None = None):
        """The `keep` best of the scored candidates, in the search's order or the scorer's."""
        if (order or self.order) == "rerank":
            scored = sorted(scored, key=lambda p: p.score, reverse=True)
        return scored[:keep]

    def with_neighbours(self, question: str, selected: list[Passage]) -> list[Passage]:
        """Add the pages before and after the best passage that continue its section."""
        if not selected:
            return selected
        best = max(selected, key=lambda p: p.score)
        have = {p.chunk_id for p in selected}
        added = []
        for page in (best.page - 1, best.page + 1):
            for passage in self.page_text(best.document_id, page):
                if passage.chunk_id not in have and same_section(passage, best):
                    added.append(passage)
        return selected + self.score(question, added)

    def search(self, question: str, component: str | None = None) -> list[Passage]:
        """What /ask reads: the selected passages, each with its score, for the gate."""
        selected = self.select(self.score(question, self.candidates(question, component)))
        return self.with_neighbours(question, selected) if self.neighbours else selected


def same_section(a: Passage, b: Passage) -> bool:
    """True if the two pages share a section: a page where two sections meet names both."""
    return bool(a.section) and bool(set(a.section.split(" | ")) & set(b.section.split(" | ")))
