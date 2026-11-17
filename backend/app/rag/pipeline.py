"""/ask, start to end. Each numbered step is one stage of the request path (plan §5.1).

3. **Retrieve** the best passages and score them (retrieval.py). The detected component
   narrows the search without ever blocking an answer (gate.scoped_search).
4. **Gate on confidence** (gate.py). If it closes, the answer is 'abstained' and no model
   is called (Rule 1, FR-10).
5. **Safety gate** (hazards.py). Passages that hold professional-only work are withheld
   from the model, and the answer will stop there with the manual's reason (Rule 3).
6. **Compose** from the passages of one manual at a time, best first, with their pages as
   images (generation.py). One manual at a time, so the model never has to choose between
   two manuals' values: it chose one silently in every test (ADR 0003).
7. **Validate** the answer against the passages (grounding.py, FR-06). A failure abstains.
   When the question names a part and the answer is a value, the next manual that names
   the part is asked too; if the two values differ, both are given, the newer manual
   first, each with its manual and print date (ADR 0004).
8. The manual's own warnings are attached ahead of the steps they concern, and every
   step, citation and source says which manual and page it came from (Rules 3 and 4).

Stages 1, 2 and the persisting half of 8 (the photograph, the detector, the session)
belong to /detect and to the end-to-end wiring (T-407).
"""

import asyncio
from dataclasses import dataclass, field
from typing import Protocol

from app.contracts import AnswerStatus, AskResponse, Citation, Hazard, Source, Step
from app.rag.gate import GateDecision, decide, names, scoped_search
from app.rag.generation import SYSTEM_PROMPT, PageImage, VisionModel, build_prompt, passage_ids
from app.rag.grounding import Grounded, GroundedStep, check
from app.rag.hazards import HazardList, Match, load
from app.rag.retrieval import Passage
from app.rag.text import part_codes, values

# Manuals asked, at most, for one question: each is one model call.
MAX_MANUALS = 3


class Search(Protocol):
    def search(self, question: str, component: str | None = None) -> list[Passage]: ...


class Images(Protocol):
    def page(self, document_id: str, page: int) -> bytes | None: ...


@dataclass
class Settings:
    threshold: float
    page_images: int = 2  # page renders sent with the passages; 0 sends text only


@dataclass
class Trace:
    """What happened, for the evaluation and the logs. Not part of the response."""

    gate: GateDecision
    scope: str = "every manual"  # or 'component', or 'widened' after the component failed
    model_calls: int = 0
    documents: list[str] = field(default_factory=list)  # the manuals asked, in order
    problems: list[str] = field(default_factory=list)  # why answers were refused
    conflict: bool = False
    stopped: bool = False  # a professional-only mark withheld passages


def by_document(passages: list[Passage]) -> dict[str, list[Passage]]:
    """The passages grouped by manual, the manual of the best-ranked passage first."""
    groups: dict[str, list[Passage]] = {}
    for passage in passages:
        groups.setdefault(passage.document_id, []).append(passage)
    return groups


def pages_of(passages: dict[str, Passage], limit: int) -> list[tuple[str, int, list[str]]]:
    """The distinct pages of the passages, best first, with the passage ids on each."""
    pages: dict[tuple[str, int], list[str]] = {}
    for pid, p in passages.items():
        pages.setdefault((p.document_id, p.page), []).append(pid)
    return [(doc, page, ids) for (doc, page), ids in list(pages.items())[:limit]]


def is_value_answer(answer: Grounded) -> bool:
    """One step that states a value: the kind of answer two manuals can disagree on."""
    return (
        answer.status == "answered"
        and len(answer.steps) == 1
        and bool(values(answer.steps[0].text))
    )


class AskPipeline:
    def __init__(
        self,
        search: Search,
        model: VisionModel,
        images: Images,
        settings: Settings,
        hazards: HazardList | None = None,
    ) -> None:
        self.search = search
        self.model = model
        self.images = images
        self.settings = settings
        self.hazards = hazards or load()

    # ------------------------------------------------------------- stages 3-4
    async def gate(self, question: str, component: str | None) -> tuple[GateDecision, str]:
        """Search and decide. Returns the decision and the scope the passages came from."""

        def run() -> tuple[GateDecision, str]:
            passages, scoped = scoped_search(self.search.search, question, component)
            gate = decide(question, passages, self.settings.threshold)
            if gate.open or not scoped:
                return gate, "component" if scoped else "every manual"
            wide = decide(question, self.search.search(question, None), self.settings.threshold)
            return (wide, "widened") if wide.open else (gate, "component")

        return await asyncio.to_thread(run)

    # ------------------------------------------------------------- stages 6-7
    async def generate(self, question: str, passages: list[Passage]) -> Grounded:
        """One model call on the passages of one manual, then the grounding check."""
        given = passage_ids(passages)
        attached: list[PageImage] = []
        for doc, page, ids in pages_of(given, self.settings.page_images):
            png = await asyncio.to_thread(self.images.page, doc, page)
            if png:
                attached.append(PageImage(doc, page, png, ids))
        prompt = build_prompt(question, given, attached)
        reply = await self.model.generate(SYSTEM_PROMPT, prompt, [i.png for i in attached])
        return check(reply, given)

    async def compose(self, question: str, passages: list[Passage], trace: Trace) -> AskResponse:
        """Stages 5 to 8 on the passages the gate let through."""
        confidence = trace.gate.confidence
        stops = self.hazards.stops(passages)
        withheld = {m.passage.chunk_id for m in stops}
        trace.stopped = bool(stops)
        codes = part_codes(question)
        answers: list[Grounded] = []
        groups = by_document([p for p in passages if p.chunk_id not in withheld])
        for document, group in list(groups.items())[:MAX_MANUALS]:
            if answers:
                # An answer is in hand. A further manual is asked only to compare a value,
                # and only if the question names a part that this manual names too.
                comparable = codes and all(names(group, code) for code in codes)
                if not (is_value_answer(answers[0]) and comparable):
                    continue
            answer = await self.generate(question, group)
            trace.model_calls += 1
            trace.documents.append(document)
            if answer.status == "abstained":
                trace.problems += answer.problems
                continue
            answers.append(answer)
            if len(answers) == 2 or not is_value_answer(answers[0]):
                break

        if not answers:
            if stops:
                return stopped(stops, confidence)
            return abstained(confidence, "; ".join(dict.fromkeys(trace.problems)))
        first = answers[0]
        differs = (
            len(answers) == 2
            and is_value_answer(answers[1])
            and values(answers[1].steps[0].text) != values(first.steps[0].text)
        )
        if differs:
            trace.conflict = True
            steps = conflicting(first, answers[1])
            return self.respond(steps, confidence, stops, None)
        reason = first.stop_reason if first.status == "professional_only" else None
        truncated = first.status == "professional_only"
        return self.respond(first.steps, confidence, stops, reason, truncated)

    async def ask(self, question: str, component: str | None = None) -> tuple[AskResponse, Trace]:
        gate, scope = await self.gate(question, component)
        trace = Trace(gate, scope)
        if not gate.open:
            return abstained(gate.confidence, gate.reason), trace
        response = await self.compose(question, gate.passages, trace)
        if response.status == AnswerStatus.abstained and scope == "component":
            # The component's manuals had no answer: the question may be about another part.
            passages = await asyncio.to_thread(self.search.search, question, None)
            wide = decide(question, passages, self.settings.threshold)
            if wide.open:
                trace.gate, trace.scope = wide, "widened"
                response = await self.compose(question, wide.passages, trace)
        return response, trace

    # ---------------------------------------------------------------- stage 8
    def respond(
        self,
        steps: list[GroundedStep],
        confidence: float,
        stops: list[Match],
        stop_reason: str | None,
        truncated: bool = False,
    ) -> AskResponse:
        cited = list({p.chunk_id: p for s in steps for p in s.passages}.values())
        hazards: list[Hazard] = []
        seen: set[str] = set()
        for number, step in enumerate(steps, start=1):
            for passage in step.passages:
                for match in self.hazards.matches(passage):
                    if match.sentence.lower() not in seen:
                        seen.add(match.sentence.lower())
                        hazards.append(
                            Hazard(
                                before_step=number,
                                text=match.sentence,
                                professional_only=match.professional_only,
                            )
                        )
        if stops:  # the procedure stops where the withheld work would begin
            truncated, stop_reason = True, stop_reason or stops[0].sentence
            cited += [
                m.passage for m in stops if m.passage.chunk_id not in {p.chunk_id for p in cited}
            ]
        return AskResponse(
            status=AnswerStatus.truncated if truncated else AnswerStatus.answered,
            steps=[
                Step(number=n, text=s.text, citation=citation(s.passages[0]))
                for n, s in enumerate(steps, start=1)
            ],
            citations=[citation(p) for p in cited],
            sources=sources(cited),
            hazards=hazards,
            confidence=confidence,
            stop_reason=stop_reason if truncated else None,
        )


# ------------------------------------------------------------------ responses
def citation(passage: Passage) -> Citation:
    figure = passage.found_by_figure or (passage.figures[0] if passage.figures else None)
    return Citation(
        document_id=passage.document_id,
        document_title=passage.document_title,
        page=passage.page,
        figure=figure,
        chunk_id=passage.chunk_id,
    )


def sources(passages: list[Passage]) -> list[Source]:
    """Rule 4: each manual used, once, and whether it is a manufacturer's manual."""
    seen: dict[str, Source] = {}
    for p in passages:
        seen.setdefault(
            p.document_id,
            Source(
                document_id=p.document_id,
                document_title=p.document_title,
                is_manufacturer_manual=p.is_manufacturer_manual,
            ),
        )
    return list(seen.values())


def abstained(confidence: float, reason: str | None) -> AskResponse:
    return AskResponse(status=AnswerStatus.abstained, confidence=confidence, stop_reason=reason)


def stopped(stops: list[Match], confidence: float) -> AskResponse:
    """Nothing may be described: the answer is the manual's reason for stopping (FR-09)."""
    passages = list({m.passage.chunk_id: m.passage for m in stops}.values())
    return AskResponse(
        status=AnswerStatus.truncated,
        citations=[citation(p) for p in passages],
        sources=sources(passages),
        hazards=[Hazard(before_step=1, text=m.sentence, professional_only=True) for m in stops],
        confidence=confidence,
        stop_reason=stops[0].sentence,
    )


def conflicting(a: Grounded, b: Grounded) -> list[GroundedStep]:
    """Two manuals, two values: both, the newer manual first, each with its manual and date."""
    newer, older = sorted([a, b], key=lambda g: g.steps[0].passages[0].published, reverse=True)
    steps = []
    for answer in (newer, older):
        p = answer.steps[0].passages[0]
        steps.append(
            GroundedStep(
                f"{p.document_title} ({p.document_id}, printed {p.published}): "
                f"{answer.steps[0].text}",
                answer.steps[0].passages,
            )
        )
    return steps
