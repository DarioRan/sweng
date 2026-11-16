"""Run the whole /ask pipeline on labelled questions, for one or more language models.

    docker compose --profile ingest --profile local run --rm -v "$PWD/bench:/bench" ingest \\
        python -m app.rag.evaluate /bench/ask_questions.json --out /bench/results \\
        --models qwen3.5:4b,gemma4:e2b --images 2,0

This is the test ADR 0003 chooses the model with. Unlike bench/run.py, which gives each
model hand-picked passages, it runs what /ask runs: the search, the gate, the safety
gate, the model with the page images, the grounding check and the comparison of manuals.
So a model is scored on the questions that reach it, and a mistake the grounding check
catches costs an answer but is not a wrong answer.

Each answer is one of:

- **right**: an answerable question answered with the expected values, citing a page
  that holds them (for a conflict: both manuals, the newer first).
- **wrong**: a wrong value or citation, or any answer to an unanswerable question. This
  is the failure the product exists to prevent.
- **lost**: an answerable question that was abstained on.
- **refused**: an unanswerable question that was abstained on. Correct.

Raw answers go to a JSON file; they quote the manuals, so --raw must be git-ignored.
"""

import argparse
import asyncio
import csv
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

import httpx
from minio import Minio
from qdrant_client import QdrantClient

from app.config import get_settings
from app.rag.generation import OllamaVisionModel
from app.rag.labels import is_source, listed, says, says_all
from app.rag.pipeline import AskPipeline, Settings
from app.rag.retrieval import Retriever
from app.rag.service import BucketImages
from app.rag.text import normalise

VERDICTS = ("right", "wrong", "lost", "refused")


def judge(question: dict, response, given: dict) -> tuple[str, str]:
    """The verdict on one response, and why. `given` maps chunk ids to the passages read."""
    answered = response.status in ("answered", "truncated")
    if "sources" not in question:
        return ("refused", "") if not answered else ("wrong", "answered an unanswerable question")
    if not answered:
        return "lost", response.stop_reason or ""
    text = " ".join(s.text for s in response.steps)
    problems = []
    for wanted in question.get("must_include", []):
        if not says_all(text, [wanted]):
            problems.append(f"missing {wanted if isinstance(wanted, str) else wanted[0]}")
    problems += [f"gives {b}" for b in question.get("must_exclude", []) if says(text, b)]
    if question.get("ordered") and not problems:
        places = [normalise(text).find(normalise(w)) for w in question["must_include"]]
        if places != sorted(places):
            problems.append("the newer manual is not first")
    cited = [given[c.chunk_id] for c in response.citations if c.chunk_id in given]
    groups = question["sources"]
    if len(groups) == 1:
        if not any(is_source(question, p) for p in cited):
            problems.append("cites no page that holds the answer")
    else:  # a conflict: a page of each manual
        pages = {(p.document_id, p.page) for p in cited}
        for group in groups:
            if not pages & {(doc, page) for doc, page in group}:
                problems.append(f"does not cite {group[0][0]}")
    return ("right", "") if not problems else ("wrong", "; ".join(problems))


def wrong_class(question: dict, classes: dict[str, list[str]]) -> str | None:
    """A component class the question's manuals do not cover, as a wrong detection would give."""
    every = sorted({c for covered in classes.values() for c in covered})
    covered = {c for doc, _ in listed(question) for c in classes.get(doc, [])}
    return next((c for c in every if c not in covered), None) if covered else None


def ensure_model(url: str, model: str) -> bool:
    """Pull the model if Ollama lacks it. Returns whether it can read images."""
    tags = httpx.get(f"{url}/api/tags", timeout=30).json()["models"]
    if not any(m["name"] in (model, f"{model}:latest") for m in tags):
        print(f"  pulling {model} ...", flush=True)
        with httpx.stream("POST", f"{url}/api/pull", json={"model": model}, timeout=None) as r:
            for line in r.iter_lines():
                if '"error"' in line:
                    raise RuntimeError(line)
    shown = httpx.post(f"{url}/api/show", json={"model": model}, timeout=60).json()
    return "vision" in shown.get("capabilities", [])


async def run(pipeline: AskPipeline, questions: list[dict], components: dict) -> list[dict]:
    rows = []
    for q in questions:
        started = time.monotonic()
        response, trace = await pipeline.ask(q["question"], components.get(q["id"]))
        seconds = time.monotonic() - started
        given = {p.chunk_id: p for p in trace.gate.passages}
        verdict, why = judge(q, response, given)
        refused_by_check = [p for p in trace.problems if "model found no answer" not in p]
        rows.append(
            {
                "id": q["id"],
                "split": q["split"],
                "answerable": "sources" in q,
                "verdict": verdict,
                "why": why,
                "status": response.status,
                "gate_open": trace.gate.open,
                "scope": trace.scope,
                "model_calls": trace.model_calls,
                "manuals": trace.documents,
                "conflict": trace.conflict,
                "check_refused": refused_by_check,
                "seconds": round(seconds, 2),
                "confidence": round(response.confidence, 3),
                "steps": [s.text for s in response.steps],
                "cited": [f"{c.document_id} p{c.page}" for c in response.citations],
                "hazards": [h.text for h in response.hazards],
                "stop_reason": response.stop_reason,
            }
        )
        print(
            f"  {q['id']:<10} {verdict:<8} calls={trace.model_calls} {seconds:5.1f}s {why}",
            flush=True,
        )
    return rows


def row(label: str, rows: list[dict]) -> str:
    def count(verdict: str) -> int:
        return sum(r["verdict"] == verdict for r in rows)

    answerable = sum(r["answerable"] for r in rows)
    called = sorted(r["seconds"] for r in rows if r["model_calls"])
    median = statistics.median(called) if called else 0.0
    p90 = called[int(0.9 * (len(called) - 1))] if called else 0.0
    cells = [
        label,
        f"**{count('right')}**/{answerable}",
        f"**{count('wrong')}**",
        str(count("lost")),
        f"{count('refused')}/{len(rows) - answerable}",
        str(sum(not r["gate_open"] for r in rows)),
        str(sum(r["model_calls"] for r in rows)),
        str(sum(bool(r["check_refused"]) for r in rows)),
        f"{median:.1f} / {p90:.1f}",
    ]
    return "| " + " | ".join(cells) + " |"


HEAD = [
    "| Model, page images | Right | Wrong | Lost | Refused | Closed at the gate "
    "| Model calls | Refused by the check | s / answer (median / 90%) |",
    "|---|---|---|---|---|---|---|---|---|",
]


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("questions", type=Path)
    parser.add_argument("--models", default=settings.llm_local_model)
    parser.add_argument(
        "--images",
        default=str(settings.ask_page_images),
        help="comma-separated page-image counts to try; 0 = text only",
    )
    parser.add_argument("--threshold", type=float, default=settings.retrieval_confidence_threshold)
    parser.add_argument(
        "--wrong-component",
        action="store_true",
        help="pass every answerable question a component class its manuals do not cover",
    )
    parser.add_argument("--provenance", type=Path, default=Path("/corpus/provenance.csv"))
    parser.add_argument("--out", type=Path, default=None, help="folder for the Markdown report")
    parser.add_argument(
        "--raw",
        type=Path,
        default=Path("/bench/data/results"),
        help="raw answers; they quote the manuals, so keep it git-ignored",
    )
    parser.add_argument(
        "--remove-after",
        action="store_true",
        help="delete each model from Ollama after its run (small disks)",
    )
    args = parser.parse_args()

    questions = json.loads(args.questions.read_text(encoding="utf-8"))["questions"]
    answerable = sum("sources" in q for q in questions)
    components: dict[str, str] = {}
    if args.wrong_component:
        with args.provenance.open(newline="", encoding="utf-8") as file:
            classes = {
                f"{r['doc_code']}-{r['revision']}": r["components"].split("|")
                for r in csv.DictReader(file)
            }
        components = {q["id"]: c for q in questions if (c := wrong_class(q, classes))}
    url = settings.llm_local_url.rstrip("/")
    retriever = Retriever(
        QdrantClient(url=settings.qdrant_url),
        settings.qdrant_collection,
        settings.embedder_model,
        settings.retrieval_scorer,
        cache_dir=settings.model_cache_dir,
    )
    s3 = Minio(
        settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        secure=settings.s3_secure,
    )
    images = BucketImages(s3, settings.s3_bucket_figures)
    version = httpx.get(f"{url}/api/version", timeout=30).json()["version"]

    intro = [
        f"# /ask end to end, {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Ollama {version}. {len(questions)} questions from `{args.questions.name}`: "
        f"{answerable} answerable, {len(questions) - answerable} not. Scorer "
        f"`{settings.retrieval_scorer}`, threshold {args.threshold:.2f}.",
    ]
    if components:
        intro += [
            "",
            f"**Wrong component.** {len(components)} answerable questions were each given a "
            "component class that their manuals do not cover, as a wrong detection or a "
            "photograph of another part would.",
        ]
    table, held_out, details, notes, raw = [], [], [], [], {}
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        try:
            sees = ensure_model(url, model)
        except (httpx.HTTPError, RuntimeError, KeyError) as err:
            notes.append(f"`{model}` did not run: {' '.join(str(err).split())[:200]}")
            continue
        for n in [int(x) for x in args.images.split(",")]:
            if n and not sees:
                notes.append(f"`{model}` cannot read images, so it ran on text only.")
                continue
            label = f"`{model}`, {n} page image{'s' if n != 1 else ''}"
            print(f"\n{label}", flush=True)
            pipeline = AskPipeline(
                retriever, OllamaVisionModel(url, model, 300), images, Settings(args.threshold, n)
            )
            rows = asyncio.run(run(pipeline, questions, components))
            raw[label] = rows
            table.append(row(label, rows))
            held_out.append(row(label, [r for r in rows if r["split"] == "test"]))
            misses = [r for r in rows if r["verdict"] in ("wrong", "lost")]
            details += ["", f"### {label}", ""]
            details += [f"- `{r['id']}` {r['verdict']}: {r['why']}" for r in misses] or ["None."]
        httpx.post(f"{url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)
        if args.remove_after:
            httpx.request("DELETE", f"{url}/api/delete", json={"model": model}, timeout=60)

    text = "\n".join(
        intro
        + ["", "## Every question", "", *HEAD, *table]
        + [
            "",
            "## The held-out questions only",
            "",
            "The threshold was chosen without these (the 'test' split).",
            "",
            *HEAD,
            *held_out,
            "",
            "- **Right, wrong, lost**: of the answerable questions. An unanswerable question "
            "that was answered also counts as wrong.",
            "- **Refused**: unanswerable questions abstained on.",
            "- **Closed at the gate**: questions abstained on before any model call.",
            "- **Refused by the check**: questions where the grounding check refused an answer "
            "the model gave. They reach the user as abstentions, or are answered from the next "
            "manual.",
            "- **s / answer**: of the questions that reached the model; depends on the machine.",
            *[f"- {note}" for note in dict.fromkeys(notes)],
            "",
            "## Wrong and lost",
            *details,
        ]
    )
    print(text)
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / f"{stamp}-ask.md").write_text(text + "\n", encoding="utf-8")
    args.raw.mkdir(parents=True, exist_ok=True)
    (args.raw / f"{stamp}-ask.json").write_text(json.dumps(raw, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
