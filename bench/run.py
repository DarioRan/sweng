"""Compare small Ollama models on the /ask task: answer from manual passages, cite, abstain.

Standard library only, so it runs in a bare Python image or straight on a host:

    docker compose --profile bench run --rm llm-bench
    python bench/run.py --models llama3.2:3b,gemma3:4b

bench/README.md explains what is measured and how to read the results.
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent

# Small models published by a major lab (Meta, Alibaba, Google, Microsoft, IBM) in Ollama's
# official library. No community fine-tunes. The first one was the project's
# LLM_LOCAL_MODEL before ADR 0003, so it is the baseline.
DEFAULT_MODELS = "llama3.2:3b,qwen3.5:4b,qwen2.5:3b,gemma4:e2b,gemma3:4b,phi4-mini,granite4.2:3b"

SYSTEM_PROMPT = """\
You are a bicycle repair assistant. You answer from the manual passages you are given, \
and from nothing else.

Rules:
1. Use only the passages. Never use what you remember about bicycle parts.
2. Check the part code in the question. A passage about another part, or about another \
bolt, does not answer it.
3. If the passages do not contain the answer, set "status" to "abstained" and leave \
"answer" empty.
4. Otherwise set "status" to "answered". Keep the answer short and keep the exact values \
from the passages (torque, sizes, tools). For a how-to question, give the steps in order.
5. If the passages say the job must not be done by the user, or must be left to a dealer, \
do not explain how to do it. That notice is the answer: set "status" to "answered" and say \
who must do the job.
6. "citations": the id of every passage you took the answer or a hazard from, for \
example ["P2"]. No others.
7. "hazards": every warning, caution or notice in the passages that applies to this job. \
An empty list if there is none.
8. If two passages give different values for the same thing on the same part, do not \
choose one. Give both values, the one from the newer manual first, name the manual each \
comes from, and cite both passages.

Reply with one JSON object and nothing else."""

# Enforced by Ollama's structured outputs. A cut-down AskResponse (backend/app/contracts.py).
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["answered", "abstained"]},
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
        "hazards": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "answer", "citations", "hazards"],
}

# The same for every model. Temperature 0 and a fixed seed make a rerun repeat the answers.
OPTIONS = {"temperature": 0, "seed": 0, "num_ctx": 4096, "num_predict": 512}


# ------------------------------------------------------------------- Ollama
def post(url: str, payload: dict | None = None):
    """Open `url` (POST if there is a payload) and turn Ollama's error body into a message."""
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(request, timeout=900)
    except urllib.error.HTTPError as err:
        body = err.read().decode(errors="replace")
        try:
            body = json.loads(body)["error"]
        except (ValueError, KeyError, TypeError):
            pass
        raise RuntimeError(body or str(err)) from err


def call(url: str, payload: dict | None = None) -> dict:
    with post(url, payload) as reply:
        return json.load(reply)


def wait_for_ollama(base: str, seconds: int = 60) -> str:
    """Return the Ollama version once the server answers; exit if it never does."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            return call(f"{base}/api/version")["version"]
        except (OSError, RuntimeError) as err:
            if time.monotonic() > deadline:
                sys.exit(f"Ollama does not answer at {base}: {err}")
            time.sleep(2)


def pull(base: str, model: str) -> None:
    """Download `model` unless Ollama already has it."""
    have = {m["name"] for m in call(f"{base}/api/tags")["models"]}
    if model in have or f"{model}:latest" in have:
        return
    print(f"  pulling {model} ...", flush=True)
    shown = 0
    with post(f"{base}/api/pull", {"model": model}) as events:
        for line in events:
            event = json.loads(line)
            if "error" in event:
                raise RuntimeError(event["error"])
            total = event.get("total", 0)
            if total > 100e6:  # only the weights are worth a progress line
                percent = 100 * event.get("completed", 0) // total
                if percent >= shown + 25:
                    shown = percent - percent % 25
                    print(f"    {shown}%", flush=True)


def ask(base: str, model: str, case: dict) -> tuple[str, float, float]:
    """Put one case to one model. Returns the reply text, seconds taken and tokens per second."""
    passages = "\n\n".join(f"[{p['id']}] {p['source']}\n{p['text']}" for p in case["passages"])
    question = f"Passages:\n\n{passages}\n\nQuestion: {case['question']}"
    reply = call(
        f"{base}/api/chat",
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            "format": ANSWER_SCHEMA,
            "options": OPTIONS,
            # Reasoning models think first by default. That spent the whole num_predict
            # budget and left qwen3.5 with an empty answer, so it is off for every model.
            "think": False,
            "stream": False,
        },
    )
    # Loading the model is a one-off cost, so it is left out of the answer time.
    seconds = (reply["total_duration"] - reply.get("load_duration", 0)) / 1e9
    generating = reply.get("eval_duration", 0) / 1e9
    tokens_per_s = reply.get("eval_count", 0) / generating if generating else 0.0
    return reply["message"]["content"], seconds, tokens_per_s


def describe(base: str, model: str) -> tuple[str, float]:
    """Where Ollama loaded the model ('GPU', 'CPU' or a split) and its size on disk in GB."""
    names = (model, f"{model}:latest")
    ran_on = "?"
    for loaded in call(f"{base}/api/ps")["models"]:
        if loaded["name"] in names and loaded.get("size"):
            share = loaded.get("size_vram", 0) / loaded["size"]
            ran_on = "GPU" if share > 0.99 else "CPU" if share == 0 else f"{share:.0%} GPU"
    size = next((m["size"] for m in call(f"{base}/api/tags")["models"] if m["name"] in names), 0)
    return ran_on, size / 1e9


# ------------------------------------------------------------------ scoring
def normalise(text: str) -> str:
    """Fold the ways of writing the same value: '9 – 11', '9 to 11 N·m' -> '9-11'."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[‐‑‒–—−]", "-", text)
    text = re.sub(r"(\d)\s*(?:n[·.⋅ ]?m|mm)?\s*(?:-|to|and)\s*(?=\d)", r"\1-", text)
    return re.sub(r"\s+", " ", text)


def find(text: str, wanted: str) -> int:
    """Where `wanted` first stands in the normalised `text` as its own word or number, or -1.

    '1.6' must not match inside '11.6' or '1.65', nor 'oil' inside 'foil'. Word endings
    stay open, so 'cool' also finds 'cooled'.
    """
    wanted = normalise(wanted)
    end = r"(?!\d|\.\d)" if wanted[-1].isdigit() else ""
    match = re.search(rf"(?<![\w.]){re.escape(wanted)}{end}", text)
    return match.start() if match else -1


def has(text: str, wanted: str) -> bool:
    return find(text, wanted) >= 0


def score(case: dict, raw: str) -> list[str]:
    """List what is wrong with one answer. An empty list means the case is passed."""
    try:
        reply = json.loads(raw)
        status = reply["status"]
        text = normalise(" ".join([reply["answer"], *reply["hazards"]]))
        cited = set(re.findall(r"P\d+", " ".join(reply["citations"]).upper()))
    except (ValueError, KeyError, TypeError):
        return ["reply is not the JSON that was asked for"]

    expect = case["expect"]
    if expect.get("status") == "abstained":
        return [] if status == "abstained" else ["answered, but the passages hold no answer"]

    problems = []
    if "status" in expect and status != expect["status"]:
        problems.append("abstained, but the answer is in the passages")
    for wanted in expect.get("must_include", []):
        options = [wanted] if isinstance(wanted, str) else wanted
        if not any(has(text, option) for option in options):
            problems.append(f"missing '{options[0]}'")
    for banned in expect.get("must_exclude", []):
        if has(text, banned):
            problems.append(f"gives '{banned}', which is not the answer")
    if expect.get("ordered"):
        places = [find(text, wanted) for wanted in expect["must_include"]]
        if -1 not in places and places != sorted(places):
            problems.append("gives the values in the wrong order: the newer manual comes first")
    # One passage from every group has to be cited, and nothing outside the groups. A group
    # has several passages when a real manual repeats the fact on several pages.
    groups = expect.get("cite_groups") or [[passage] for passage in expect["cite"]]
    allowed = {passage for group in groups for passage in group}
    if not cited <= allowed or any(not cited & set(group) for group in groups):
        wanted = " and ".join("/".join(group) for group in groups)
        problems.append(f"cited {sorted(cited) or 'nothing'}, expected {wanted}")
    return problems


# ---------------------------------------------------------------- reporting
def run_model(base: str, model: str, cases: list[dict]) -> dict:
    pull(base, model)
    answers = []
    for case in cases:
        raw, seconds, tokens_per_s = ask(base, model, case)
        problems = score(case, raw)
        print(f"  {case['id']:<9} {'ok' if not problems else 'FAIL  ' + '; '.join(problems)}")
        answers.append(
            {
                "case": case["id"],
                "category": case["category"],
                "problems": problems,
                "seconds": round(seconds, 2),
                "tokens_per_s": round(tokens_per_s, 1),
                "raw": raw,
            }
        )
    ran_on, size_gb = describe(base, model)
    call(f"{base}/api/generate", {"model": model, "keep_alive": 0})  # free memory for the next
    return {"model": model, "ran_on": ran_on, "size_gb": round(size_gb, 1), "answers": answers}


def report(runs: list[dict], failed: dict[str, str], cases: list[dict], version: str) -> str:
    """The Markdown summary: one row per model, best first, then every failed case."""
    categories = list(dict.fromkeys(case["category"] for case in cases))
    size = {c: sum(1 for case in cases if case["category"] == c) for c in categories}

    def passed(run: dict, category: str | None = None) -> int:
        return sum(
            1 for a in run["answers"] if not a["problems"] and category in (None, a["category"])
        )

    def median(run: dict, key: str) -> float:
        return statistics.median(a[key] for a in run["answers"])

    runs = sorted(runs, key=lambda run: (-passed(run), median(run, "seconds")))
    head = ["Model", "Passed", *(f"{c} ({size[c]})" for c in categories)]
    head += ["s / answer", "tokens / s", "Ran on", "Size"]
    lines = [
        f"# LLM comparison, {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Ollama {version}, {len(cases)} cases, same prompt and settings for every model.",
        "",
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
    ]
    for run in runs:
        row = [f"`{run['model']}`", f"**{passed(run)}/{len(cases)}**"]
        row += [str(passed(run, c)) for c in categories]
        row += [f"{median(run, 'seconds'):.1f}", f"{median(run, 'tokens_per_s'):.0f}"]
        row += [run["ran_on"], f"{run['size_gb']} GB"]
        lines.append("| " + " | ".join(row) + " |")
    lines += [
        "",
        "A case is passed only when the status, the facts and the citations are all right.",
        "The times are medians and depend on the machine; compare them within one run only.",
    ]
    for model, error in failed.items():
        lines += ["", f"`{model}` did not run: {error}"]
    lines += ["", "## Failed cases"]
    for run in runs:
        lines += ["", f"### {run['model']}", ""]
        misses = [a for a in run["answers"] if a["problems"]]
        lines += [f"- `{a['case']}`: {'; '.join(a['problems'])}" for a in misses] or ["None."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--ollama-url", default=os.environ.get("OLLAMA_URL") or "http://localhost:11434"
    )
    parser.add_argument(
        "--models",
        default=os.environ.get("BENCH_MODELS") or DEFAULT_MODELS,
        help="comma-separated Ollama model tags",
    )
    parser.add_argument("--cases", type=Path, default=HERE / "cases.json")
    parser.add_argument("--out", type=Path, default=HERE / "results")
    args = parser.parse_args()

    base = args.ollama_url.rstrip("/")
    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    version = wait_for_ollama(base)

    runs, failed = [], {}
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"\n{model}", flush=True)
        try:
            runs.append(run_model(base, model, cases))
        except (OSError, RuntimeError, KeyError) as err:
            # One model that cannot be pulled or loaded must not lose the others' results.
            failed[model] = " ".join(str(err).split())
            print(f"  skipped: {failed[model]}", flush=True)

    summary = report(runs, failed, cases, version)
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    (args.out / f"{stamp}.md").write_text(summary, encoding="utf-8")
    (args.out / f"{stamp}.json").write_text(
        json.dumps({"ollama": version, "options": OPTIONS, "runs": runs}, indent=2),
        encoding="utf-8",
    )
    print(f"\n{summary}\nSaved to {args.out / stamp}.md and .json")


if __name__ == "__main__":
    main()
