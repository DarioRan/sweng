"""/ask without any store or model: scope, gate, safety gate, grounding, pipeline (ADR 0004).

The search, the model and the page images are fakes, so these run in CI.
"""

import asyncio

import pytest

from app.rag.gate import decide, scoped_search
from app.rag.grounding import check
from app.rag.hazards import HazardList, load
from app.rag.labels import is_source
from app.rag.pipeline import AskPipeline, Settings
from app.rag.retrieval import Passage
from app.rag.text import contains_value, normalise, part_codes, values

TORQUE_ROW = (
    "BR-R9270 Caliper mounting screw 6 - 8 N·m 4 mm hexagon wrench\n"
    "BR-R9170 Caliper mounting screw 6 - 8 N·m\nFlare nut 5 - 6 N·m"
)


def passage(text: str, *, doc="DM-TORQUE-04", page=8, score=0.9, published="2023-12", n=1):
    return Passage(
        chunk_id=f"{doc}:p{page}:c{n}",
        document_id=doc,
        document_title=f"Manual {doc}",
        page=page,
        section="Hydraulic Disc Brake Caliper",
        published=published,
        text=text,
        figures=[f"{doc}/p{page:03d}-1.png"],
        score=score,
    )


# --------------------------------------------------------------------- text
@pytest.mark.parametrize(
    ("raw", "folded"),
    [("6 – 8 N·m", "6-8 n·m"), ("6 to 8 N·m", "6-8 n·m"), ("ST- R8020", "st-r8020")],
)
def test_normalise_folds_the_ways_of_writing_a_value(raw: str, folded: str) -> None:
    assert normalise(raw) == folded


def test_part_codes_are_found_and_manual_codes_are_not() -> None:
    assert part_codes("bleed screw on an ST- R8020 lever, see DM-TORQUE-04") == {"ST-R8020"}
    assert part_codes("BR-R9270 and RD-M820") == {"BR-R9270", "RD-M820"}


def test_part_codes_expand_a_list_that_gives_the_prefix_once() -> None:
    assert part_codes("BR-R9100/R8000/R7000") == {"BR-R9100", "BR-R8000", "BR-R7000"}
    assert part_codes("ST-R7020 / R7025: 2.5 mm") == {"ST-R7020", "ST-R7025"}
    assert part_codes("CS-M8100 / 12-speed, BB-MT800 / 73 mm") == {"CS-M8100", "BB-MT800"}


def test_values_ignore_step_numbers_but_keep_ranges_and_sizes() -> None:
    assert values("1. Tighten to 6 - 8 N·m with a 2.5 mm wrench") == {"6-8", "2.5"}


def test_one_end_of_a_printed_range_is_not_a_value() -> None:
    assert contains_value("2.5 - 3 N·m (SL-RS25)", "2.5-3")
    assert not contains_value("2.5 - 3 N·m (SL-RS25)", "3")
    assert not contains_value("2.5 - 3 N·m (SL-RS25)", "2.5")
    assert contains_value("2.5 - 3 N·m with a 3 mm hexagon wrench", "3")


def test_a_value_is_matched_whole() -> None:
    assert contains_value("tighten to 11.6 N·m", "11.6")
    assert not contains_value("tighten to 11.6 N·m", "1.6")
    assert contains_value("4 - 6 N·m", "4-6")
    assert not contains_value("4 - 7 N·m", "4-6")


# --------------------------------------------------------------------- gate
def test_gate_closes_below_the_threshold_and_passes_nothing_on() -> None:
    gate = decide("torque?", [passage(TORQUE_ROW, score=0.2)], threshold=0.5)
    assert not gate.open and gate.passages == []
    assert "threshold" in gate.reason


def test_gate_closes_when_no_manual_names_the_part() -> None:
    assert "BR-Z9999" in decide("Torque for the BR-Z9999 caliper?", [], 0.5).reason
    gate = decide("Torque for the BR-Z9999 caliper?", [passage(TORQUE_ROW)], threshold=0.5)
    assert not gate.open and "BR-Z9999" in gate.reason


def test_gate_accepts_a_part_its_manual_names_when_the_page_does_not() -> None:
    page = passage("B-axle\n10 - 12 N·m")
    page.parts = ["RD-M8100", "RD-M9100"]
    assert decide("B-axle torque on an RD-M8100?", [page], 0.5).open
    assert not decide("B-axle torque on an RD-M9999?", [page], 0.5).open


def test_an_open_gate_passes_every_selected_passage_on() -> None:
    ranked = [passage("other", score=0.1, n=2), passage(TORQUE_ROW, score=0.9)]
    gate = decide("Caliper mounting screw torque on BR-R9270?", ranked, 0.5)
    assert gate.open and gate.confidence == 0.9 and len(gate.passages) == 2


# -------------------------------------------------------------------- scope
class FakeSearch:
    """Passages by component (None = every manual). Records what it was asked."""

    def __init__(self, everywhere: list[Passage], by_component: dict | None = None) -> None:
        self.everywhere = everywhere
        self.by_component = by_component or {}
        self.asked: list[tuple[str, str | None]] = []

    def search(self, question: str, component: str | None = None) -> list[Passage]:
        self.asked.append((question, component))
        return self.everywhere if component is None else self.by_component.get(component, [])


def test_without_a_component_every_manual_is_searched() -> None:
    search = FakeSearch([passage("x")])
    passages, scoped = scoped_search(search.search, "How tight?", None)
    assert not scoped and passages == search.everywhere


def test_a_vague_question_is_searched_in_the_component_with_its_name_added() -> None:
    pedal = passage("Pedal 35 - 55 N·m", doc="DM-PD0001-05", score=0.60)
    search = FakeSearch([passage("x", score=0.61)], {"pedal": [pedal]})
    passages, scoped = scoped_search(search.search, "How tight should this be?", "pedal")
    assert scoped and passages == [pedal]
    assert search.asked[-1] == ("pedal: How tight should this be?", "pedal")


def test_a_question_about_another_part_is_not_held_to_the_photographed_one() -> None:
    brakes = passage("Bleeding the brakes", doc="DM-MADBR01-08", score=0.80)
    pedals = passage("Pedal 35 - 55 N·m", doc="DM-PD0001-05", score=0.65)
    search = FakeSearch([brakes], {"pedal": [pedals]})
    passages, scoped = scoped_search(search.search, "How do I bleed the brakes?", "pedal")
    assert not scoped and passages == [brakes]


# ---------------------------------------------------------------- grounding
def given() -> dict[str, Passage]:
    return {"P1": passage(TORQUE_ROW)}


def reply(text: str, cite: str = "P1", status: str = "answered") -> dict:
    return {"status": status, "steps": [{"text": text, "passages": [cite]}]}


def test_a_grounded_answer_passes() -> None:
    assert check(reply("6-8 N·m"), given()).status == "answered"


def test_a_value_not_in_the_cited_passage_abstains() -> None:
    result = check(reply("5-7 N·m"), given())
    assert result.status == "abstained"
    assert "5-7" in result.problems[0]


def test_a_value_on_the_cited_page_passes_even_in_its_other_passage() -> None:
    page = {"P1": passage("Flare nut", n=1), "P2": passage("5 - 6 N·m", n=2)}
    assert check(reply("5-6 N·m", cite="P1"), page).status == "answered"
    other = {"P1": passage("Flare nut", page=8), "P2": passage("5 - 6 N·m", page=9)}
    assert check(reply("5-6 N·m", cite="P1"), other).status == "abstained"


def test_a_value_may_not_come_from_a_source_that_is_not_the_manufacturer() -> None:
    guide = passage("Tighten the pedal to 40 N·m", doc="REPAIR-GUIDE", page=3)
    guide.is_manufacturer_manual = False
    assert check(reply("40 N·m"), {"P1": guide}).status == "abstained"
    assert check(reply("Grease the pedal thread first"), {"P1": guide}).status == "answered"


def test_a_source_that_is_not_the_manufacturer_is_declared() -> None:
    guide = passage("Grease the pedal thread before fitting 35 - 55 N·m", doc="REPAIR-GUIDE")
    guide.is_manufacturer_manual = False
    response, _, _ = ask([guide], "How do I fit the pedal?")
    assert response.status == "abstained"  # the fake model quotes the line with its value
    words = passage("Grease the pedal thread before fitting", doc="REPAIR-GUIDE")
    words.is_manufacturer_manual = False

    class Quotes(FakeModel):
        async def generate(self, system: str, user: str, images: list[bytes]) -> dict:
            return reply("Grease the pedal thread before fitting")

    pipeline = AskPipeline(FakeSearch([words]), Quotes(), OnePng(), Settings(0.5, 0))
    response, _ = asyncio.run(pipeline.ask("How do I fit the pedal?"))
    assert [s.is_manufacturer_manual for s in response.sources] == [False]


def test_a_step_without_a_known_citation_abstains() -> None:
    assert check(reply("6-8 N·m", cite="P9"), given()).status == "abstained"


def test_a_part_code_no_passage_names_abstains() -> None:
    assert check(reply("On the BR-R8170, 6-8 N·m"), given()).status == "abstained"


def test_citations_written_loosely_are_understood() -> None:
    assert check(reply("6-8 N·m", cite="[p1]"), given()).status == "answered"


def test_professional_only_needs_a_passage_that_says_so() -> None:
    stop = {"status": "professional_only", "steps": [], "stop_reason": "Dealer only"}
    assert check(stop, given()).status == "abstained"
    dealer = {"P1": passage("If the pistons protrude further than normal, consult a dealer.")}
    assert check(stop, dealer).status == "professional_only"


def test_invalid_json_abstains() -> None:
    assert check({"status": "invalid", "raw": "{"}, given()).status == "abstained"


# ------------------------------------------------------------------ hazards
HOT = "The calipers and disc brake rotor will become hot when the brakes are operated."


def test_a_hazard_is_the_manuals_own_sentence() -> None:
    page = passage(f"Remove the wheel.\n{HOT}\nInstall the pads.")
    matches = load().matches(page)
    assert [m.sentence for m in matches] == [HOT]
    assert not matches[0].professional_only


def test_the_preface_of_every_manual_is_not_a_hazard() -> None:
    preface = passage(
        "WARNING Failure to follow the instructions could result in death or serious injury.\n"
        "This dealer's manual is intended primarily for use by professional bicycle mechanics."
    )
    assert load().matches(preface) == []


def test_being_sent_to_a_dealer_is_marked_professional_only() -> None:
    page = passage("If the chain keeps skipping during use, consult the place of purchase.")
    assert [m.professional_only for m in load().matches(page)] == [True]


def test_a_warning_that_refers_back_keeps_the_sentence_before_it() -> None:
    page = passage(
        "Do not let oil get on the rotor. Failure to do so may result in serious injury.\n"
        "Lock ring\nWear gloves when removing the lock ring."
    )
    assert [m.sentence for m in load().matches(page)] == [
        "Do not let oil get on the rotor. Failure to do so may result in serious injury.",
        "Wear gloves when removing the lock ring.",
    ]


def test_a_sentence_broken_by_the_pdf_is_mended() -> None:
    page = passage("If bolts become dam-\naged, the bicycle may fall over.")
    assert load().matches(page)[0].sentence == "If bolts become damaged, the bicycle may fall over."


# ----------------------------------------------------------------- pipeline
class FakeModel:
    """Answers with the first value printed in the passages it was given, and counts calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def generate(self, system: str, user: str, images: list[bytes]) -> dict:
        self.calls.append((user, len(images)))
        for line in user.splitlines():
            found = sorted(values(line))
            if found and not line.startswith(("[P", "Image")):
                return {"status": "answered", "steps": [{"text": line, "passages": ["P1"]}]}
        return {"status": "abstained", "steps": []}


class OnePng:
    def page(self, document_id: str, page: int) -> bytes | None:
        return b"png"


def ask(search, question: str, component: str | None = None, hazards: HazardList | None = None):
    if isinstance(search, list):
        search = FakeSearch(search)
    model = FakeModel()
    pipeline = AskPipeline(search, model, OnePng(), Settings(0.5, 2), hazards)
    response, trace = asyncio.run(pipeline.ask(question, component))
    return response, trace, model


def test_an_abstention_at_the_gate_calls_no_model() -> None:
    response, trace, model = ask([passage(TORQUE_ROW, score=0.1)], "Torque on BR-R9270?")
    assert response.status == "abstained"
    assert model.calls == [] and trace.model_calls == 0
    assert response.stop_reason


def test_an_answer_cites_its_manual_page_and_figure() -> None:
    response, _, _ = ask([passage("BR-R9270 mounting screw 6 - 8 N·m")], "Torque on BR-R9270?")
    assert response.status == "answered"
    step = response.steps[0]
    assert (step.citation.document_id, step.citation.page) == ("DM-TORQUE-04", 8)
    assert step.citation.figure == "DM-TORQUE-04/p008-1.png"
    assert [s.is_manufacturer_manual for s in response.sources] == [True]


def test_two_manuals_that_disagree_give_both_values_newer_first() -> None:
    brake = passage(
        "ST-R7020 bleed screw 2.5 mm", doc="DM-RADBR01-11", page=24, published="2025-04"
    )
    chart = passage("ST-R7020 bleed screw 2 mm", doc="DM-TORQUE-04", page=13)
    response, trace, model = ask([chart, brake], "Which wrench for the bleed screw on ST-R7020?")
    assert trace.conflict and len(model.calls) == 2
    assert response.status == "answered"
    assert [s.citation.document_id for s in response.steps] == ["DM-RADBR01-11", "DM-TORQUE-04"]
    assert "2025-04" in response.steps[0].text and "2023-12" in response.steps[1].text


def test_the_prompt_says_which_of_the_questions_parts_a_manual_covers() -> None:
    page = passage("Lock ring 30 - 50 N·m", doc="DM-MACS010-02")
    page.parts = ["CS-M8200", "CS-M9200"]
    _, _, model = ask([page], "Lock ring torque of a CS-M8200 cassette?")
    assert "This manual covers CS-M8200." in model.calls[0][0]
    assert "CS-M9200" not in model.calls[0][0]


def test_each_call_sees_one_manual_with_its_page_images() -> None:
    a = passage("ST-R7020 2.5 mm", doc="DM-RADBR01-11", page=24)
    b = passage("ST-R7020 2 mm", doc="DM-TORQUE-04", page=13)
    _, _, model = ask([a, b], "Bleed screw wrench on ST-R7020?")
    first, _ = model.calls
    assert "DM-RADBR01-11" in first[0] and "DM-TORQUE-04" not in first[0]
    assert first[1] == 1  # one page, one image


def test_a_second_manual_about_another_part_is_not_asked() -> None:
    a = passage("ST-R7020 2.5 mm", doc="DM-RADBR01-11", page=24)
    b = passage("ST-R9270 2 mm", doc="DM-TORQUE-04", page=13)
    _, trace, _ = ask([a, b], "Bleed screw wrench on ST-R7020?")
    assert trace.model_calls == 1 and not trace.conflict


def test_without_a_part_code_manuals_are_not_compared() -> None:
    a = passage("Lock ring 30 - 50 N·m", doc="DM-MACS001-05", page=9)
    b = passage("Lock ring 40 N·m", doc="DM-RACS001-03", page=8)
    response, trace, _ = ask([a, b], "What is the lock ring torque?")
    assert trace.model_calls == 1 and len(response.steps) == 1


def test_when_the_first_manual_has_no_answer_the_next_is_asked() -> None:
    a = passage("Routing the cable along the frame", doc="DM-RD0001-06", page=6)
    b = passage("Mounting bolt 8 - 10 N·m", doc="DM-RARD010-07", page=20)
    response, trace, _ = ask([a, b], "What is the mounting bolt torque?")
    assert trace.documents == ["DM-RD0001-06", "DM-RARD010-07"]
    assert response.steps[0].citation.document_id == "DM-RARD010-07"


def test_the_photographed_part_does_not_block_a_question_about_another() -> None:
    """Pedals in the photograph, a braking problem in the question."""
    pedals = passage("Clean the pedal body with a cloth", doc="DM-PD0001-05", score=0.79)
    brakes = passage("Pad thickness limit 0.5 mm", doc="DM-MADBR01-08", score=0.80)
    search = FakeSearch([brakes], {"pedal": [pedals]})
    response, trace, _ = ask(search, "When are the brake pads worn out?", component="pedal")
    assert trace.scope == "widened"
    assert response.steps[0].citation.document_id == "DM-MADBR01-08"


def test_a_warning_comes_from_the_list_ahead_of_its_step() -> None:
    page = passage(f"Pad axle 0.2 - 0.4 N·m\n{HOT}")
    response, _, _ = ask([page], "Pad axle torque?")
    assert [(h.before_step, h.text) for h in response.hazards] == [(1, HOT)]


STOP_LIST = HazardList.from_dict(
    {"entries": [{"id": "bleed", "kind": "stop", "pattern": "must be bled by a dealer"}]}
)


def test_professional_only_work_is_withheld_from_the_model_and_stops_the_answer() -> None:
    allowed = passage("Pad axle 0.2 - 0.4 N·m", page=8)
    marked = passage("The brake must be bled by a dealer. Open the bleed screw 1/8 turn.", page=9)
    response, trace, model = ask(
        [allowed, marked], "How do I service the brake?", hazards=STOP_LIST
    )
    assert response.status == "truncated" and trace.stopped
    assert response.stop_reason == "The brake must be bled by a dealer."
    assert all("bleed screw" not in prompt for prompt, _ in model.calls)
    assert [s.text for s in response.steps] == ["Pad axle 0.2 - 0.4 N·m"]


def test_when_everything_is_professional_only_nothing_is_described() -> None:
    marked = passage("The brake must be bled by a dealer. Open the bleed screw 1/8 turn.")
    response, _, model = ask([marked], "How do I bleed the brake?", hazards=STOP_LIST)
    assert response.status == "truncated" and response.steps == [] and model.calls == []
    assert response.hazards[0].professional_only


# ------------------------------------------------------------------- labels
def test_a_page_counts_as_a_source_when_listed_or_when_it_names_the_part_and_value() -> None:
    question = {
        "question": "Torque for the caliper mounting screw on a BR-R9270?",
        "sources": [[["DM-RADBR01-11", 45]]],
        "must_include": ["6-8"],
    }
    assert is_source(question, passage("anything", doc="DM-RADBR01-11", page=45))
    assert is_source(question, passage(TORQUE_ROW))  # the torque chart repeats it
    assert not is_source(question, passage("BR-R9270 flare nut 5 - 6 N·m"))
