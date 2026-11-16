"""Rule 1: decide, before any model call, whether the passages can answer the question.

Two checks, both cheap and both deterministic:

1. **The part named.** Every part code in the question must be named by a selected
   passage or by the manual it is from. The search is already limited to the manuals that
   name the part (retrieval.py), so a question about BR-Z9999 finds nothing and stops
   here: no manual covers that part, however similar its neighbours' torque tables look.
2. **Confidence.** The best passage's score must reach the threshold, which is
   calibrated on labelled questions (`python -m app.rag.calibrate`, ADR 0004).

When the gate closes, /ask answers 'abstained' and the model is not called (FR-10). When
it opens, every selected passage goes on to the model: the threshold decides whether to
answer, not which passages to read.
"""

import re
from dataclasses import dataclass

from app.rag.retrieval import Passage
from app.rag.text import normalise, part_codes


@dataclass
class GateDecision:
    open: bool
    confidence: float  # the best passage's score, 0 when nothing was found
    passages: list[Passage]  # every selected passage when open, none when closed
    reason: str | None = None  # why it closed


def names(passages: list[Passage], code: str) -> bool:
    """True if a passage, or the manual it is from, names the part.

    The page often does not: "B-axle 10 - 12 N·m" applies to the models in the manual's
    list. A model number also counts when it is listed without its prefix, as in
    'ST-R7020/R7025'.
    """
    model = code.split("-", 1)[1].lower()
    pattern = rf"(?<![a-z0-9]){re.escape(model)}(?![0-9])"
    for p in passages:
        if code in p.parts or re.search(pattern, normalise(f"{p.section}\n{p.text}")):
            return True
    return False


def decide(question: str, passages: list[Passage], threshold: float) -> GateDecision:
    codes = part_codes(question)
    if not passages:
        if codes:
            return GateDecision(
                False, 0.0, [], f"no indexed manual names {', '.join(sorted(codes))}"
            )
        return GateDecision(False, 0.0, [], "the search found nothing")
    missing = sorted(code for code in codes if not names(passages, code))
    if missing:
        return GateDecision(False, 0.0, [], f"no passage names {', '.join(missing)}")
    confidence = best_score(passages)
    if confidence < threshold:
        return GateDecision(
            False,
            confidence,
            [],
            f"no passage reaches the threshold ({confidence:.2f} < {threshold:.2f})",
        )
    return GateDecision(True, confidence, passages)


# How much better the best passage of every manual must score than the best passage of
# the component's manuals for the question to be read as being about something else.
# Set on the questions of bench/scope_questions.json and the labelled set (ADR 0004);
# to be recalibrated on real detections when the detector exists (T-407).
SCOPE_MARGIN = 0.02


def best_score(passages: list[Passage]) -> float:
    return max((p.score for p in passages), default=0.0)


def scoped_search(search, question: str, component: str | None) -> tuple[list[Passage], bool]:
    """The passages for a question, and whether they are limited to the component's manuals.

    The photograph says what the user is looking at, not what the problem is: a photo of
    the pedals with "how do I bleed the brakes?" is a question for the brake manuals. So
    the detected component is a hint, never a wall:

    - Without a component, or when every manual together holds a clearly better passage
      than the component's manuals do, the search is not limited.
    - Otherwise it is limited to the component's manuals, and the component's name is
      added to the question, so that "how tight should this be?" finds the pedal's torque.

    `search(question, component)` is Retriever.search.
    """
    everywhere = search(question, None)
    if not component:
        return everywhere, False
    within = search(question, component)
    if best_score(everywhere) - best_score(within) > SCOPE_MARGIN:
        return everywhere, False
    return search(f"{component.replace('_', ' ')}: {question}", component), True
