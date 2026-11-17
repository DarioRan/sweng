"""Rule 3 hazard gate (T-503): warnings ahead of the step, professional-only work stops.

Each procedure below follows the order of the matching procedure in the Shimano
dealer's manual cited next to it, with the steps reworded.
"""

import csv
import re
from pathlib import Path

import pytest

from app.contracts import AnswerStatus
from app.safety import HAZARDS, RetrievedStep, apply_hazards
from app.safety.hazards import LEVELS
from app.vision import LABELS

PROVENANCE = Path(__file__).resolve().parents[2] / "docs" / "corpus" / "provenance.csv"


def procedure(component: str, document_id: str, *texts: str) -> list[RetrievedStep]:
    return [
        RetrievedStep(number=i, text=t, component=component, document_id=document_id, page=1)
        for i, t in enumerate(texts, start=1)
    ]


def hazard_steps(result) -> dict[str, int]:
    """Map each hazard to the step it is placed before, keyed by its cited text."""
    return {h.text: h.before_step for h in result.hazards}


def first_before(result, needle: str) -> int:
    matches = [h.before_step for h in result.hazards if needle.lower() in h.text.lower()]
    assert matches, f"no hazard mentioning {needle!r} in {[h.text for h in result.hazards]}"
    return matches[0]


def assert_hazards_ahead_of_kept_steps(result) -> None:
    kept = {s.number for s in result.steps}
    for h in result.hazards:
        if h.professional_only:
            assert h.before_step not in kept
        else:
            assert h.before_step in kept


# ----------------------------------------------------------- the list itself
def test_hazard_ids_are_unique() -> None:
    ids = [h.id for h in HAZARDS]
    assert len(ids) == len(set(ids))


def test_every_hazard_names_known_components_and_a_level() -> None:
    for h in HAZARDS:
        assert h.components, h.id
        for c in h.components:
            assert c == "*" or c in LABELS, (h.id, c)
        assert h.level in LEVELS, h.id


def test_every_pattern_compiles() -> None:
    for h in HAZARDS:
        for p in h.patterns:
            re.compile(p)


def test_professional_only_hazards_give_a_reason() -> None:
    for h in HAZARDS:
        if h.professional_only:
            assert h.reason, h.id


def test_list_has_professional_only_marks() -> None:
    assert sum(h.professional_only for h in HAZARDS) >= 5


def test_every_source_is_a_manual_in_the_corpus() -> None:
    if not PROVENANCE.exists():
        pytest.skip("docs/ not mounted (container run)")
    with PROVENANCE.open(encoding="utf-8") as f:
        codes = {row["doc_code"] for row in csv.DictReader(f)}
    for h in HAZARDS:
        assert h.source.document_id in codes, (h.id, h.source.document_id)
        assert h.source.pages and all(p > 0 for p in h.source.pages), h.id


# ------------------------------------- hazardous procedures that may go ahead
def test_cassette_removal_warns_before_the_lock_ring_step() -> None:
    # DM-LACS001 p.7, "Removing the cassette sprocket"
    result = apply_hazards(
        procedure(
            "cassette",
            "DM-LACS001",
            "Hold the cassette with the sprocket tool on a sprocket smaller than the middle one.",
            "Turn the lock ring tool to loosen and take off the lock ring.",
            "Slide the sprockets off the freehub body.",
        )
    )
    assert result.status is AnswerStatus.answered
    assert len(result.steps) == 3
    assert first_before(result, "lock ring") == 2
    assert_hazards_ahead_of_kept_steps(result)


def test_rear_derailleur_cable_warns_about_the_wheel_before_securing_it() -> None:
    # DM-MARD001 p.17, "Connection and securing of the inner cable"
    result = apply_hazards(
        procedure(
            "rear_derailleur",
            "DM-MARD001",
            "Set the shifter in its initial position.",
            "Secure the inner cable to the rear derailleur.",
            "Trim the excess and fit the inner end cap.",
        )
    )
    assert result.status is AnswerStatus.answered
    assert first_before(result, "wheel still") == 2
    assert_hazards_ahead_of_kept_steps(result)


def test_rotor_installation_warns_about_sharp_edges_and_heat() -> None:
    # DM-LADBR01 p.13, "Installing the disc brake rotor"
    result = apply_hazards(
        procedure(
            "disc_rotor",
            "DM-LADBR01",
            "Check that the spokes are laced as shown.",
            "Set the disc brake rotor on the hub and secure it with the rotor lock ring.",
        )
    )
    assert result.status is AnswerStatus.answered
    assert first_before(result, "edges are sharp") == 2
    assert first_before(result, "get hot") == 2
    # The cassette lock-ring warning belongs to cassettes only.
    assert not any("sprockets" in h.text for h in result.hazards)
    assert_hazards_ahead_of_kept_steps(result)


def test_chain_shortening_warns_about_cut_position_and_pin_tool() -> None:
    # DM-CN0001 pp.8-9, chain cutter use and chain length
    result = apply_hazards(
        procedure(
            "chain",
            "DM-CN0001",
            "Put the chain on the largest sprocket and the largest chainring.",
            "Cut the chain to length with the chain cutter.",
            "Join the chain with a new reinforced connecting pin.",
        )
    )
    assert result.status is AnswerStatus.answered
    assert first_before(result, "do not cut it where") == 2
    assert first_before(result, "connecting pin and chain tool") == 2
    assert_hazards_ahead_of_kept_steps(result)


def test_brake_pad_replacement_is_not_stopped_but_warned() -> None:
    # DM-LADBR01 pp.33-35, "Replacing the brake pads": pushing the pistons back
    # is part of a normal pad change and must not stop the procedure.
    result = apply_hazards(
        procedure(
            "disc_brake_caliper",
            "DM-LADBR01",
            "Remove the wheel from the frame.",
            "Take out the old brake pads.",
            "Clean the pistons and the area around them.",
            "Push the pistons straight back with a flat tool.",
            "Fit the new brake pads with the pad spring.",
            "Squeeze the lever until it is firm, then take out the pad spacer and refit the wheel.",
        )
    )
    assert result.status is AnswerStatus.answered
    assert len(result.steps) == 6
    assert first_before(result, "pad spacer") == 1
    assert first_before(result, "oil and grease off the pads") == 2
    assert first_before(result, "bed-in") == 5
    assert_hazards_ahead_of_kept_steps(result)


# --------------------------------------- professional-only: the procedure stops
STOPPED = [
    pytest.param(
        # DM-LADBR01 pp.37-40, "SHIMANO genuine mineral oil replacement"
        procedure(
            "disc_brake_caliper",
            "DM-LADBR01",
            "Position the bicycle so the brake lever is level with the ground.",
            "Remove the bleed screw and O-ring and fit the oil funnel.",
            "Add the oil through the bleed nipple until no bubbles come out.",
        ),
        2,
        "hydraulic",
        id="hydraulic-bleed",
    ),
    pytest.param(
        # DM-LADBR01 pp.23-28, "Installing the brake hose"
        procedure(
            "disc_brake_caliper",
            "DM-LADBR01",
            "Route the brake hose to its final position.",
            "Check the length of the hose against the lever.",
            "Cut the brake hose at the mark with the hose cutter.",
            "Press the connector insert into the hose.",
        ),
        3,
        "hose",
        id="hydraulic-hose-cut",
    ),
    pytest.param(
        # DM-GN0001 p.76, "Removing a QUICK-LINK"
        procedure(
            "chain",
            "DM-GN0001",
            "Shift the chain to the smallest sprocket.",
            "Open the QUICK-LINK with the link pliers.",
        ),
        2,
        "QUICK-LINK",
        id="quick-link-removal",
    ),
    pytest.param(
        # DM-LADBR01 p.10: the pistons must not be removed
        procedure(
            "disc_brake_caliper",
            "DM-LADBR01",
            "Remove the pistons from the caliper to clean them.",
            "Refit the pistons.",
        ),
        1,
        "pistons",
        id="caliper-piston-removal",
    ),
    pytest.param(
        # DM-MARD001 pp.33-36, "Replacing the plate, P-tension spring, and switch lever"
        procedure(
            "rear_derailleur",
            "DM-MARD001",
            "Set the switch lever in the OFF position.",
            "Remove the plate stopper pin.",
            "Turn the plate to release the P-tension spring.",
        ),
        2,
        "clutch",
        id="rd-clutch-teardown",
    ),
]


@pytest.mark.parametrize(("steps", "stop_at", "reason_word"), STOPPED)
def test_professional_only_step_stops_the_procedure(steps, stop_at, reason_word) -> None:
    result = apply_hazards(steps)

    assert result.status is AnswerStatus.truncated
    # Only the steps before the stop reach the model.
    assert [s.number for s in result.steps] == list(range(1, stop_at))
    assert result.stop_reason
    assert f"step {stop_at}" in result.stop_reason
    assert reason_word.lower() in result.stop_reason.lower()
    assert "professional" in result.stop_reason
    # The stopped step and the ones after it are never described.
    for s in steps[stop_at - 1 :]:
        assert s.text not in result.stop_reason
        assert all(s.text not in h.text for h in result.hazards)
    # The stop is reported as a professional-only hazard at the stopped step.
    pro = [h for h in result.hazards if h.professional_only]
    assert len(pro) == 1 and pro[0].before_step == stop_at
    assert_hazards_ahead_of_kept_steps(result)


# ------------------------------------------------------------------ mechanics
def test_steps_are_taken_in_number_order() -> None:
    steps = procedure(
        "disc_brake_caliper",
        "DM-LADBR01",
        "Position the bicycle so the brake lever is level with the ground.",
        "Add the oil through the bleed nipple.",
    )
    result = apply_hazards(list(reversed(steps)))
    assert [s.number for s in result.steps] == [1]
    assert result.status is AnswerStatus.truncated


def test_each_hazard_is_stated_once_before_its_first_step() -> None:
    result = apply_hazards(
        procedure(
            "chain",
            "DM-GN0001",
            "Fit a new QUICK-LINK on the chain ends.",
            "Pedal backwards and check that the QUICK-LINK is fully seated.",
        )
    )
    quick = [h for h in result.hazards if "single-use" in h.text]
    assert len(quick) == 1 and quick[0].before_step == 1


def test_hazard_text_carries_its_level_and_manual_citation() -> None:
    result = apply_hazards(
        procedure("v_brake", "DM-GN0001", "Fit the power modulator to the V-brake.")
    )
    texts = [h.text for h in result.hazards]
    assert any(t.startswith("WARNING:") and "Shimano DM-GN0001, p. 81" in t for t in texts)


def test_a_procedure_without_hazards_passes_unchanged() -> None:
    steps = procedure(
        "shift_brake_lever",
        "DM-SL0002",
        "Turn the barrel adjuster a quarter turn.",
        "Shift through all the gears and listen for noise.",
    )
    result = apply_hazards(steps)
    assert result.status is AnswerStatus.answered
    assert result.steps == steps
    assert result.hazards == []
    assert result.stop_reason is None


def test_an_empty_procedure_is_answered_with_nothing() -> None:
    result = apply_hazards([])
    assert result.status is AnswerStatus.answered
    assert result.steps == [] and result.hazards == []
