"""Choose how /ask selects its passages and where it abstains, on labelled questions.

    docker compose --profile ingest run --rm -v "$PWD/bench:/bench" ingest \\
        python -m app.rag.calibrate /bench/ask_questions.json --out /bench/results

No language model is called: this measures the search and the gate alone (retrieval.py,
gate.py). For each scorer it answers three questions, in this order:

1. **Which passages?** The five best in the search's order, or in the scorer's, with or
   without the neighbouring pages of the best one. The variant that puts the answer page
   in front of the model for the most questions wins (*reached*). A tie goes to the
   simpler variant: the search's order, no neighbours.
2. **Where to abstain?** The highest threshold that still keeps at least 95% of the
   answerable questions that variant reaches (*kept*). The rule was fixed before looking
   at the numbers: a lost answer has no second chance, while a question let through by
   mistake still meets the model, which may abstain, and the grounding check.
3. **How much does it stop?** The unanswerable questions the gate closes on before any
   model call (*refused*).

Everything is chosen on the 'calibrate' split and reported on the 'test' split too, so
the threshold is not scored on the questions it was tuned on.
"""

import argparse
import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from qdrant_client import QdrantClient

from app.config import get_settings
from app.rag.gate import SCOPE_MARGIN, best_score, decide, scoped_search
from app.rag.labels import is_source
from app.rag.retrieval import Passage, Retriever

KEEP_SHARE = 0.95
GRID = [round(x / 100, 2) for x in range(0, 100)]
# (order, neighbours), simplest first: a tie in step 1 goes to the earlier one.
VARIANTS = [("hybrid", False), ("hybrid", True), ("rerank", False), ("rerank", True)]
SPLITS = ("calibrate", "test")


def label(variant: tuple[str, bool]) -> str:
    order, neighbours = variant
    name = "search order" if order == "hybrid" else "scorer order"
    return f"{name}{', with neighbours' if neighbours else ''}"


@dataclass
class Scored:
    q: dict  # the labelled question
    selected: dict[tuple[str, bool], list[Passage]] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.q["id"]

    @property
    def split(self) -> str:
        return self.q["split"]

    @property
    def question(self) -> str:
        return self.q["question"]

    @property
    def answerable(self) -> bool:
        return "sources" in self.q

    def holds(self, passages: list[Passage]) -> bool:
        return any(is_source(self.q, p) for p in passages)

    def reached(self, variant) -> bool:
        return self.holds(self.selected[variant])

    def kept(self, variant, threshold: float) -> bool:
        gate = decide(self.question, self.selected[variant], threshold)
        return gate.open and self.holds(gate.passages)

    def refused(self, variant, threshold: float) -> bool:
        return not decide(self.question, self.selected[variant], threshold).open


def score(retriever: Retriever, questions: list[dict]) -> list[Scored]:
    out = []
    for q in questions:
        item = Scored(q)
        candidates = retriever.score(q["question"], retriever.candidates(q["question"]))
        for order, neighbours in VARIANTS:
            chosen = retriever.select(candidates, order=order)
            if neighbours:
                chosen = retriever.with_neighbours(q["question"], chosen)
            item.selected[(order, neighbours)] = chosen
        out.append(item)
    return out


def reach(scored: list[Scored], variant, split: str) -> tuple[int, int]:
    answerable = [s for s in scored if s.answerable and s.split == split]
    return sum(s.reached(variant) for s in answerable), len(answerable)


def rates(scored: list[Scored], variant, threshold: float, split: str) -> tuple[int, int, int, int]:
    """kept, of the answerable questions reached; refused, of the unanswerable ones."""
    mine = [s for s in scored if s.split == split]
    reached = [s for s in mine if s.answerable and s.reached(variant)]
    unanswerable = [s for s in mine if not s.answerable]
    return (
        sum(s.kept(variant, threshold) for s in reached),
        len(reached),
        sum(s.refused(variant, threshold) for s in unanswerable),
        len(unanswerable),
    )


def separation(scored: list[Scored], variant, split: str) -> float:
    """How well the best score alone tells a reached question from an unanswerable one:
    the share of such pairs in which the reached one scores higher (AUC). 1.0 is perfect,
    0.5 is chance. It does not depend on any threshold."""
    mine = [s for s in scored if s.split == split]

    def best(s: Scored) -> float:
        return max((p.score for p in s.selected[variant]), default=0.0)

    good = [best(s) for s in mine if s.answerable and s.reached(variant)]
    bad = [best(s) for s in mine if not s.answerable]
    pairs = [(g > b) + 0.5 * (g == b) for g in good for b in bad]
    return sum(pairs) / len(pairs) if pairs else 0.0


def choose_variant(scored: list[Scored]):
    return max(VARIANTS, key=lambda v: (reach(scored, v, "calibrate")[0], -VARIANTS.index(v)))


def choose_threshold(scored: list[Scored], variant) -> float:
    base = rates(scored, variant, 0.0, "calibrate")[0]
    best = 0.0
    for threshold in GRID:
        if rates(scored, variant, threshold, "calibrate")[0] >= KEEP_SHARE * base:
            best = threshold
    return best


def component_scope(
    retriever: Retriever,
    questions: list[dict],
    scope_questions: list[dict],
    classes: dict[str, list[str]],
    threshold: float,
) -> list[str]:
    """What the detected component does to the answers, when it is right and when it is wrong.

    Right: a class the answer's manual covers. Wrong: a class it does not cover, as when
    the photograph shows the pedals and the question is about the brakes.
    """
    every = sorted({c for covered in classes.values() for c in covered})
    search = retriever.search
    counts = {key: 0 for key in ("none", "right hard", "right", "wrong hard", "wrong")}
    total = 0
    for q in questions:
        docs = {doc for group in q.get("sources", []) for doc, _ in group}
        covered = {c for doc in docs for c in classes.get(doc, [])}
        wrong = next((c for c in every if c not in covered), None)
        if not docs or not covered or wrong is None:
            continue  # unanswerable, or only on the torque chart, which covers every class
        total += 1
        item, text, right = Scored(q), q["question"], sorted(covered)[0]

        def kept(passages, item=item, text=text) -> bool:
            gate = decide(text, passages, threshold)
            return gate.open and item.holds(gate.passages)

        counts["none"] += kept(search(text, None))
        counts["right hard"] += kept(search(text, right))
        counts["right"] += kept(scoped_search(search, text, right)[0])
        counts["wrong hard"] += kept(search(text, wrong))
        counts["wrong"] += kept(scoped_search(search, text, wrong)[0])
    lines = [
        "## The detected component: a hint, not a wall",
        "",
        f"With the default scorer at threshold {threshold:.2f}. The component is what the "
        "detector names in the photograph. `/ask` uses it through `scoped_search` (gate.py): "
        "limited to the component's manuals, with its name added to the question, unless "
        f"every manual together holds a passage scoring more than {SCOPE_MARGIN} higher.",
        "",
        f"### On the {total} labelled questions whose manual does not cover every class",
        "",
        "*Kept*: the gate opens with the answer page among the passages.",
        "",
        "| Component given | How it is used | Kept |",
        "|---|---|---|",
        f"| None | - | {counts['none']}/{total} |",
        f"| The right class | Hard filter | {counts['right hard']}/{total} |",
        f"| The right class | `scoped_search` (what /ask does) | {counts['right']}/{total} |",
        f"| A wrong class | Hard filter | {counts['wrong hard']}/{total} |",
        f"| A wrong class | `scoped_search` (what /ask does) | {counts['wrong']}/{total} |",
        "",
        "When the scoped passages give no answer, /ask searches every manual once more "
        "(pipeline.py). This table stops at the gate and does not count that second chance.",
        "",
    ]
    if scope_questions:
        lines += [
            "### On vague and mismatched questions",
            "",
            "Vague: the question does not say what it is about, the photograph does. "
            "Mismatch: the photograph shows one part, the problem is with another. *From the "
            "expected class*: how many of the selected passages come from a manual of the "
            "class that should answer (the torque chart, which covers every class, not counted).",
            "",
            "| Question | Photo shows | Should be answered from | Search used "
            "| Best score | Gate | From the expected class |",
            "|---|---|---|---|---|---|---|",
        ]
        for q in scope_questions:
            passages, scoped = scoped_search(search, q["question"], q["component"])
            gate = decide(q["question"], passages, threshold)
            specific = [
                p
                for p in passages
                if q["expect"] in classes.get(p.document_id, [])
                and len(classes[p.document_id]) < len(every)
            ]
            lines.append(
                f"| {q['id']} {q['kind']}: {q['question']} | `{q['component']}` "
                f"| `{q['expect']}` | {'component' if scoped else 'every manual'} "
                f"| {best_score(passages):.2f} | {'open' if gate.open else 'closed'} "
                f"| {len(specific)}/{len(passages)} |"
            )
        lines.append("")
    return lines


def report_scorer(name: str, scored: list[Scored]) -> tuple[list[str], dict]:
    variant = choose_variant(scored)
    threshold = choose_threshold(scored, variant)
    lines = [f"## `{name}`", "", "### 1. Which passages", ""]
    lines += [
        "| Passages given to the gate | Calibrate: reached | Test: reached |",
        "|---|---|---|",
    ]
    for v in VARIANTS:
        cells = [f"{a}/{b}" for a, b in (reach(scored, v, split) for split in SPLITS)]
        name_cell = f"**{label(v)}**" if v == variant else label(v)
        lines.append(f"| {name_cell} | {cells[0]} | {cells[1]} |")
    lines += ["", f"Chosen: **{label(variant)}**.", "", "### 2. Where to abstain", ""]
    lines += [
        "| Threshold | Calibrate: kept | Calibrate: refused | Test: kept | Test: refused |",
        "|---|---|---|---|---|",
    ]
    summary = {"variant": variant, "threshold": threshold}
    for t in sorted({0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, threshold}):
        row = [f"**{t:.2f}**" if t == threshold else f"{t:.2f}"]
        for split in SPLITS:
            kept, reached, refused, unanswerable = rates(scored, variant, t, split)
            row += [f"{kept}/{reached}", f"{refused}/{unanswerable}"]
            if t == threshold:
                summary[split] = (kept, reached, refused, unanswerable)
        lines.append("| " + " | ".join(row) + " |")
    lines += [
        "",
        f"Chosen threshold: **{threshold:.2f}**.",
        "",
        "### 3. Every question, at the chosen variant and threshold",
        "",
        "| Question | Split | Answerable | Best score | Answer page reached | Gate |",
        "|---|---|---|---|---|---|",
    ]
    for s in scored:
        passages = s.selected[variant]
        gate = decide(s.question, passages, threshold)
        verdict = "open" if gate.open else f"closed: {gate.reason}"
        reached_cell = ("yes" if s.reached(variant) else "**no**") if s.answerable else "-"
        lines.append(
            f"| {s.id} | {s.split} | {'yes' if s.answerable else 'no'} | {gate.confidence:.3f} "
            f"| {reached_cell} | {verdict} |"
        )
    lines.append("")
    for split in SPLITS:
        summary[f"reach_{split}"] = reach(scored, variant, split)
        summary[f"auc_{split}"] = separation(scored, variant, split)
    return lines, summary


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("questions", type=Path)
    parser.add_argument("--scorers", default=settings.retrieval_scorer, help="comma-separated")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--provenance", type=Path, default=Path("/corpus/provenance.csv"))
    parser.add_argument("--scope", type=Path, default=None, help="scope_questions.json")
    args = parser.parse_args()

    questions = json.loads(args.questions.read_text(encoding="utf-8"))["questions"]
    answerable = sum("sources" in q for q in questions)
    qdrant = QdrantClient(url=settings.qdrant_url)
    lines = [
        f"# Passage selection and abstention threshold, {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"{len(questions)} questions from `{args.questions.name}`: {answerable} answerable, "
        f"{len(questions) - answerable} not. No language model is called.",
        "",
        "- **reached**: answerable questions whose answer page is among the passages selected.",
        "- **kept**: of those reached, the ones the gate lets through with the answer page.",
        "- **refused**: unanswerable questions the gate closes on, before any model call.",
        "- **separation**: how well the best score alone tells a reached question from an "
        "unanswerable one (AUC: 1.0 perfect, 0.5 chance), whatever the threshold.",
        "",
        f"Rule for the threshold: the highest one that keeps at least {KEEP_SHARE:.0%} of the "
        "reached questions on the calibrate split. `dense` is not a reranker: it is the "
        "embedder's own similarity, the baseline a reranker has to beat.",
        "",
    ]
    overview = [
        "| Scorer | Passages | Threshold | Calibrate: reached | kept | refused | separation "
        "| Test: reached | kept | refused | separation |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    sections, thresholds = [], {}
    for name in [n.strip() for n in args.scorers.split(",") if n.strip()]:
        print(f"\n{name}", flush=True)
        retriever = Retriever(
            qdrant,
            settings.qdrant_collection,
            settings.embedder_model,
            name,
            cache_dir=settings.model_cache_dir,
        )
        body, s = report_scorer(name, score(retriever, questions))
        sections += body
        thresholds[name] = s["threshold"]
        row = [f"`{name}`", label(s["variant"]), f"{s['threshold']:.2f}"]
        for split in SPLITS:
            kept, reached, refused, unanswerable = s[split]
            total = s[f"reach_{split}"][1]
            row += [f"{reached}/{total}", f"{kept}/{reached}", f"{refused}/{unanswerable}"]
            row.append(f"{s[f'auc_{split}']:.2f}")
        overview.append("| " + " | ".join(row) + " |")
        print(overview[-1], flush=True)
    scope = []
    if settings.retrieval_scorer in thresholds and args.provenance.is_file():
        with args.provenance.open(newline="", encoding="utf-8") as file:
            classes = {
                f"{row['doc_code']}-{row['revision']}": row["components"].split("|")
                for row in csv.DictReader(file)
            }
        retriever = Retriever(
            qdrant,
            settings.qdrant_collection,
            settings.embedder_model,
            settings.retrieval_scorer,
            cache_dir=settings.model_cache_dir,
        )
        extra = []
        if args.scope and args.scope.is_file():
            extra = json.loads(args.scope.read_text(encoding="utf-8"))["questions"]
        scope = component_scope(
            retriever, questions, extra, classes, thresholds[settings.retrieval_scorer]
        )
    text = "\n".join(lines + overview + [""] + scope + sections)
    print(text)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"{datetime.now():%Y%m%d-%H%M%S}-calibration.md"
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
