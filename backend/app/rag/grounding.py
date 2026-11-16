"""Check the model's answer against the passages it was given. Any failure abstains.

The model is told to answer only from the passages (generation.py); this makes sure it
did, with checks that do not depend on a model (FR-06):

- Every step cites at least one passage it was given.
- Every value in a step (a torque, a size, a count) is printed on a page that step cites.
  A value from memory, or from a page the step does not cite, fails here. So does one end
  of a printed range given as if it were the value.
- Every part code in the answer is named by a passage or by its manual. An answer about
  BR-R9170 to a question the manuals of BR-R9270 were retrieved for fails here.
- A value must be printed in a manufacturer's manual. Another source may explain, but
  no specification may come from it (Rule 4).
- 'professional_only' needs a passage that says so (dealer, professional, ...).

A refused answer costs the user a minute; a confident wrong value can cost a brake. So a
single failed check abstains the whole answer, with the reason. A step is never dropped
on its own: a procedure with a step missing is worse than no procedure.

What this cannot catch: a value that is printed in the cited passage but belongs to
another row of the same table. Showing the model the page as an image is aimed at that
(generation.py), and the cited page is always shown to the user.
"""

import re
from dataclasses import dataclass, field

from app.rag.retrieval import Passage
from app.rag.text import contains_value, normalise, part_codes, values

_PROFESSIONAL = re.compile(
    r"dealer|professional|qualified|bicycle shop|specialist|place of purchase|distributor", re.I
)


@dataclass
class GroundedStep:
    text: str
    passages: list[Passage]


@dataclass
class Grounded:
    status: str  # answered | abstained | professional_only
    steps: list[GroundedStep] = field(default_factory=list)
    stop_reason: str | None = None
    problems: list[str] = field(default_factory=list)  # why it was abstained


def ungrounded_values(text: str, passages: list[Passage]) -> list[str]:
    """The values in `text` that none of the passages prints."""
    return sorted(v for v in values(text) if not any(contains_value(p.text, v) for p in passages))


def check(reply: dict, given: dict[str, Passage]) -> Grounded:
    status = reply.get("status")
    if status == "abstained":
        return Grounded("abstained", problems=["the model found no answer in the passages"])
    if status not in ("answered", "professional_only"):
        return Grounded("abstained", problems=["the model's reply is not the JSON asked for"])

    problems: list[str] = []
    steps: list[GroundedStep] = []
    for n, step in enumerate(reply.get("steps") or [], start=1):
        text = str(step.get("text", "")).strip()
        if not text:
            continue
        cited = [given[pid] for pid in dict.fromkeys(ids(step.get("passages"))) if pid in given]
        if not cited:
            problems.append(f"step {n} cites no passage it was given")
            continue
        pages = same_pages(cited, given)
        missing = ungrounded_values(text, pages)
        if missing:
            problems.append(f"step {n} gives {', '.join(missing)}, not printed in its passages")
        # Rule 4: a value may come only from a manufacturer's manual.
        official = [p for p in pages if p.is_manufacturer_manual]
        unofficial = [v for v in ungrounded_values(text, official) if v not in missing]
        if unofficial:
            problems.append(
                f"step {n} gives {', '.join(unofficial)}, printed only in a passage that is "
                "not from a manufacturer's manual"
            )
        steps.append(GroundedStep(text, cited))

    everything = list(given.values())
    for code in sorted(part_codes(" ".join(s.text for s in steps))):
        model = code.split("-", 1)[1].lower()
        if not any(code in p.parts or model in normalise(p.text) for p in everything):
            problems.append(f"the answer names {code}, which no passage names")

    stop_reason = (reply.get("stop_reason") or "").strip() or None
    if status == "professional_only":
        if not any(_PROFESSIONAL.search(p.text) for p in everything):
            problems.append("the answer stops for a professional, but no passage says so")
        if not (steps or stop_reason):
            problems.append("the answer stops for a professional without saying why")
    elif not steps:
        problems.append("the answer has no step")

    if problems:
        return Grounded("abstained", problems=problems)
    return Grounded(status, steps, stop_reason)


def same_pages(cited: list[Passage], given: dict[str, Passage]) -> list[Passage]:
    """Every passage given from the pages cited. A long page is several passages, and the
    citation the user sees is the page."""
    pages = {(p.document_id, p.page) for p in cited}
    return [p for p in given.values() if (p.document_id, p.page) in pages]


def ids(raw) -> list[str]:
    """Passage ids as the model wrote them, tidied: 'p2', '[P2]', 'P2, P3' -> ['P2', 'P3']."""
    if isinstance(raw, str):
        raw = [raw]
    return [f"P{n}" for item in raw or [] for n in re.findall(r"P\s*(\d+)", str(item).upper())]
