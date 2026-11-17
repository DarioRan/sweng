"""Rule 3: hazards ahead of the step, professional-only work stops the procedure (T-503).

This runs on the retrieved procedure *before* the model is called. It is plain,
deterministic code, so the model can neither drop a warning nor describe a step it
should not:

- every hazard that matches a step is returned with ``before_step`` set to that
  step, so the answer states it ahead of the step, never after;
- the first step that matches a professional-only hazard ends the procedure. That
  step and every later one are removed before generation, the status becomes
  ``truncated``, and ``stop_reason`` says why without describing the step.

The hazard list itself is ``hazards.json``, written from the Shimano dealer's
manuals (see ``README.md`` in this folder).
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from app.contracts import AnswerStatus, Hazard

ANY_COMPONENT = "*"
LEVELS = ("danger", "warning", "caution")


class RetrievedStep(BaseModel):
    """One numbered step of a retrieved procedure, as retrieval (T-307) hands it over."""

    number: int = Field(ge=1)
    text: str
    component: str  # a class name from categories.json
    document_id: str
    page: int


class HazardSource(BaseModel):
    document_id: str
    revision: str
    pages: list[int]


class HazardEntry(BaseModel):
    id: str
    components: list[str]
    level: str
    text: str
    patterns: list[str]
    professional_only: bool = False
    reason: str | None = None  # required when professional_only
    source: HazardSource

    def applies_to(self, step: RetrievedStep) -> bool:
        if ANY_COMPONENT not in self.components and step.component not in self.components:
            return False
        return any(p.search(step.text) for p in _compiled(self))

    def citation(self) -> str:
        pages = ", ".join(str(p) for p in self.source.pages)
        label = "p." if len(self.source.pages) == 1 else "pp."
        return f"Shimano {self.source.document_id}, {label} {pages}"

    def as_hazard(self, before_step: int) -> Hazard:
        return Hazard(
            before_step=before_step,
            text=f"{self.level.upper()}: {self.text} ({self.citation()})",
            professional_only=self.professional_only,
        )


@dataclass
class GateResult:
    """What generation may use: only ``steps`` reach the model."""

    status: AnswerStatus
    steps: list[RetrievedStep]
    hazards: list[Hazard] = field(default_factory=list)
    stop_reason: str | None = None


_PATTERNS: dict[str, list[re.Pattern[str]]] = {}


def _compiled(entry: HazardEntry) -> list[re.Pattern[str]]:
    if entry.id not in _PATTERNS:
        _PATTERNS[entry.id] = [re.compile(p, re.IGNORECASE) for p in entry.patterns]
    return _PATTERNS[entry.id]


def load_hazards(path: Path | None = None) -> tuple[HazardEntry, ...]:
    path = path or Path(__file__).with_name("hazards.json")
    raw = json.loads(path.read_text(encoding="utf-8"))["hazards"]
    return tuple(HazardEntry.model_validate(h) for h in raw)


HAZARDS: tuple[HazardEntry, ...] = load_hazards()


def stop_reason_for(entry: HazardEntry, step_number: int) -> str:
    return (
        f"Stopped before step {step_number}: this needs a professional mechanic. "
        f"{entry.reason} Take the bike to a bicycle dealer. ({entry.citation()})"
    )


def apply_hazards(
    steps: list[RetrievedStep],
    hazards: tuple[HazardEntry, ...] = HAZARDS,
) -> GateResult:
    """Attach hazards ahead of their steps, and cut the procedure at professional-only work.

    Each hazard is reported once, before the first step it applies to. Steps are
    taken in number order.
    """
    ordered = sorted(steps, key=lambda s: s.number)
    kept: list[RetrievedStep] = []
    found: list[Hazard] = []
    seen: set[str] = set()

    for step in ordered:
        matching = [h for h in hazards if h.applies_to(step)]

        stop = next((h for h in matching if h.professional_only), None)
        if stop is not None:
            # The step is not kept, so the model never sees or describes it.
            # Warnings already attached to earlier steps stay; the stop itself
            # is reported as a professional-only hazard at this step.
            found.append(stop.as_hazard(before_step=step.number))
            return GateResult(
                status=AnswerStatus.truncated,
                steps=kept,
                hazards=found,
                stop_reason=stop_reason_for(stop, step.number),
            )

        for h in matching:
            if h.id not in seen:
                seen.add(h.id)
                found.append(h.as_hazard(before_step=step.number))
        kept.append(step)

    return GateResult(status=AnswerStatus.answered, steps=kept, hazards=found)
