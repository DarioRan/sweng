"""Build LLM test cases from the real index: each question with the chunks a search returns.

    docker compose --profile ingest run --rm -v "$PWD/bench:/bench" ingest \\
        python -m app.corpus.cases /bench/corpus_questions.json /bench/data/corpus-cases.json

The output holds manual text, so it goes to bench/data/, which is git-ignored. It is in
the format bench/run.py reads. A question whose page the search did not return becomes a
case the model must abstain on, because that is what the model would then face.
"""

import json
import re
import sys
from pathlib import Path

from app.config import get_settings
from app.corpus.ingest import connect, search


def _plain(text: str) -> str:
    """Lower case with nothing around a hyphen, so 'ST- R8020' and '6 - 8' can be found."""
    return re.sub(r"\s*-\s*", "-", " ".join(text.lower().split()))


def _names_it(question: dict, text: str) -> bool:
    """True if the passage names the question's part and holds every expected value."""
    if "anchor" not in question:
        return False
    wanted = [question["anchor"], *question["must_include"]]
    return all(_plain(w) in _plain(text) for w in wanted)


def build(question: dict, hits: list) -> dict | None:
    """One case, or None when a conflict lost one of its two sides in the search."""
    sources = question.get("sources", [])
    passages, groups = [], [[] for _ in sources]
    for n, hit in enumerate(hits, start=1):
        payload = hit.payload
        where = f"{payload['document_id']}, page {payload['page']}"
        passages.append(
            {
                "id": f"P{n}",
                "source": f"{where}, published {payload['published']}",
                "text": payload["text"],
            }
        )
        for group, pages in zip(groups, sources, strict=True):
            listed = [payload["document_id"], payload["page"]] in pages
            if listed or (len(sources) == 1 and _names_it(question, payload["text"])):
                group.append(f"P{n}")
    case = {k: question[k] for k in ("id", "category", "question")}
    case["passages"] = passages
    if not sources or (len(sources) == 1 and not groups[0]):
        case["expect"] = {"status": "abstained"}
    elif not all(groups):
        return None
    else:
        case["expect"] = {
            "status": "answered",
            "must_include": question["must_include"],
            "must_exclude": question.get("must_exclude", []),
            "ordered": question.get("ordered", False),
            "cite_groups": groups,
        }
    return case


def main() -> None:
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    settings = get_settings()
    stores = connect(settings, settings.qdrant_collection)
    cases = []
    for question in json.loads(source.read_text(encoding="utf-8"))["questions"]:
        case = build(question, search(stores, question["question"]))
        if case is None:
            print(f"{question['id']}: LEFT OUT, the search returned only one side of the conflict")
            continue
        cases.append(case)
        found = case["expect"].get("cite_groups")
        missed = "sources" in question and not found
        note = "  SEARCH MISSED ITS PAGE, so the model must abstain" if missed else ""
        print(f"{case['id']}: answer in {found or 'no passage'}{note}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"cases": cases}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(cases)} cases to {target}")


if __name__ == "__main__":
    main()
