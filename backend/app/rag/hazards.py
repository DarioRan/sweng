"""The safety gate (Rule 3): hazards and professional-only work, matched against a list.

Deterministic, and outside the model. The list is hazards.json. It is applied twice:

- **Before generation.** A passage that matches a 'stop' mark is withheld from the model,
  so the model cannot describe that work. The answer then stops, with the manual's
  sentence as the stated reason (FR-09).
- **After the answer is checked.** Every sentence of a cited passage that matches the
  list is attached ahead of the first step taken from that passage, in the manual's own
  words (US-06). The model is not asked for hazards and cannot leave one out.

A hazard is never written by us or by the model: its text is the manual's sentence.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.rag.retrieval import Passage

LIST = Path(__file__).with_name("hazards.json")

# A sentence ends at . ! ? before a capital, or at a bullet.
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])|\s*[•\uf06c\uf0b7]\s*")
# A printed line shorter than this that does not end a sentence is a label or a heading
# ('Lock ring', 'Pad axle 0.2 - 0.4 N·m'), not the start of the sentence on the next line.
_LABEL = 45
# A warning that only makes sense with the sentence before it: that sentence is kept with it.
_REFERS_BACK = re.compile(
    r"^(if that happens|if this happens|failure to do so|doing so|doing otherwise|otherwise"
    r"|if you do so|if not|in that case|this may|this could|this will)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Entry:
    id: str
    kind: str  # hazard | consult | stop
    pattern: re.Pattern


@dataclass(frozen=True)
class Match:
    entry: Entry
    sentence: str  # the manual's own words
    passage: Passage

    @property
    def professional_only(self) -> bool:
        return self.entry.kind in ("consult", "stop")


@dataclass(frozen=True)
class HazardList:
    entries: tuple[Entry, ...]
    ignore: tuple[re.Pattern, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "HazardList":
        return cls(
            tuple(
                Entry(e["id"], e["kind"], re.compile(e["pattern"], re.IGNORECASE))
                for e in data["entries"]
            ),
            tuple(re.compile(p, re.IGNORECASE) for p in data.get("ignore", [])),
        )

    def matches(self, passage: Passage) -> list[Match]:
        """The passage's sentences that match the list, in reading order, once each.

        A sentence that matches several entries is reported for the gravest: stop, then
        consult, then hazard.
        """
        found: dict[str, Match] = {}
        previous = ""
        for sentence in sentences(passage.text):
            before, previous = previous, sentence
            if any(pattern.search(sentence) for pattern in self.ignore):
                continue
            hits = [e for e in self.entries if e.pattern.search(sentence)]
            if not hits:
                continue
            if before and _REFERS_BACK.match(sentence):
                sentence = f"{before} {sentence}"
            gravest = min(hits, key=lambda e: ("stop", "consult", "hazard").index(e.kind))
            found.setdefault(sentence.lower(), Match(gravest, sentence, passage))
        return list(found.values())

    def stops(self, passages: list[Passage]) -> list[Match]:
        """The 'stop' marks among the passages: work the user must not be walked through."""
        return [m for p in passages for m in self.matches(p) if m.entry.kind == "stop"]


def sentences(text: str) -> list[str]:
    """The sentences of a passage, each as the manual prints it, with wrapped lines joined."""
    runs: list[str] = []
    previous = ""
    for line in (line.strip() for line in text.split("\n")):
        if not line:
            previous = ""
            continue
        continues = (
            runs
            and previous
            and previous[-1] not in ".!?"
            and (len(previous) >= _LABEL or line[0].islower())
        )
        if continues:
            runs[-1] = f"{runs[-1]} {line}"
        else:
            runs.append(line)
        previous = line
    found = []
    for run in runs:
        run = re.sub(r"([a-z])- ([a-z])", r"\1\2", run)  # a word the PDF broke: 'dam- aged'
        found += [s.strip() for s in _SENTENCE.split(run) if s and len(s.strip()) > 12]
    return found


@lru_cache
def load(path: Path = LIST) -> HazardList:
    return HazardList.from_dict(json.loads(path.read_text(encoding="utf-8")))
