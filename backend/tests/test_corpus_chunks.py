"""Chunking loses no text, respects the embedder's limit and keeps steps whole (T-203b)."""

import random

import pytest

from app.corpus.chunks import body, chunk_page, clean, heading, page_sections, published


def _page(steps: int, seed: int = 0, style: str = "old") -> str:
    """Manual-like text: an intro, then numbered steps of a few lines each."""
    rng = random.Random(seed)
    lines = ["Replacing the part", "Note: remove the wheel first."]
    for n in range(1, steps + 1):
        first = f"word{n}a word{n}b word{n}c"
        lines.append(f"{n}. {first}" if style == "old" else str(n))
        if style == "new":
            lines.append(first)
        lines += [f"detail{n}x{i} more{n}x{i}" for i in range(rng.randint(0, 3))]
    return "\n".join(lines)


def _ink(text: str) -> str:
    """The text with all whitespace removed: what must survive chunking unchanged."""
    return "".join(text.split())


@pytest.mark.parametrize("style", ["old", "new"])
@pytest.mark.parametrize("limit", [60, 200, 1000, 100_000])
def test_every_character_is_in_exactly_one_chunk_in_order(style: str, limit: int) -> None:
    text = _page(40, style=style)
    assert _ink("".join(chunk_page(text, limit))) == _ink(text)


def test_an_unbroken_run_longer_than_a_chunk_keeps_its_place() -> None:
    text = "before one two " + "x" * 500 + " after three"
    chunks = chunk_page(text, limit=60)
    assert _ink("".join(chunks)) == _ink(text)
    assert all(len(chunk) <= 60 for chunk in chunks)


@pytest.mark.parametrize("limit", [60, 200, 1000])
def test_no_chunk_is_larger_than_the_limit(limit: int) -> None:
    assert all(len(chunk) <= limit for chunk in chunk_page(_page(40), limit))
    # Text with no break at all is still cut, at the limit.
    assert all(len(chunk) <= limit for chunk in chunk_page("x" * 5000, limit))


def test_a_page_that_fits_is_one_chunk() -> None:
    text = _page(6)
    assert chunk_page(text, limit=len(text)) == [text]


@pytest.mark.parametrize("style", ["old", "new"])
def test_a_long_page_is_cut_between_steps_not_inside_one(style: str) -> None:
    chunks = chunk_page(_page(40, style=style), limit=300)
    assert len(chunks) > 1
    for chunk in chunks[1:]:
        first = chunk.split("\n")[0]
        # Each later chunk opens on a step: "7. ..." or a bare "7".
        assert first.split(".")[0].isdigit(), first


def test_the_size_function_decides_not_the_character_count() -> None:
    text = _page(40)
    by_words = chunk_page(text, limit=30, size=lambda s: len(s.split()))
    assert all(len(chunk.split()) <= 30 for chunk in by_words)
    assert _ink("".join(by_words)) == _ink(text)


def test_an_empty_page_gives_no_chunks() -> None:
    assert chunk_page("", 100) == []
    assert chunk_page(" \n\n ", 100) == []


def test_clean_collapses_whitespace_and_leader_dots_but_keeps_lines() -> None:
    assert clean("a  b \n c\n\n\n\nd\u00a0e ") == "a b\nc\n\nd e"
    assert clean("INSTALLATION ..............................6") == "INSTALLATION ... 6"


def test_body_drops_the_page_number_and_the_continuation_line() -> None:
    assert body("12\nMAINTENANCE\n1. Remove it.", 12) == "MAINTENANCE\n1. Remove it."
    assert body("Adjustment\nChain length\n14", 14) == "Adjustment\nChain length"
    assert body("30\nTo be continued on next page\nINSTALLATION", 30) == "INSTALLATION"


def test_body_takes_the_page_number_once_and_leaves_other_numbers() -> None:
    # Page 3 that ends with its number and happens to open on step 3.
    assert body("3\nAdjust the bleed screw.\n3", 3) == "3\nAdjust the bleed screw."
    assert body("5\n1. Tighten to 5 N·m\n2", 7) == "5\n1. Tighten to 5 N·m\n2"
    assert body("12", 12) == ""


def test_heading_keeps_real_titles_and_model_codes() -> None:
    assert heading("Installing  the crank arms") == "Installing the crank arms"
    assert heading("CS-M9100") == "CS-M9100"
    assert heading("10-51T") == "10-51T"
    assert heading("\uf06e 2x10") == "2x10"  # the bullet glyph goes, the title stays


def test_heading_rejects_the_bookmarks_word_generates() -> None:
    assert heading("O_24584") == ""
    assert heading("Word のしおり") == ""


def test_page_sections_carries_a_section_over_the_pages_it_spans() -> None:
    bookmarks = [(2, "NOTICE"), (4, "INSTALLATION"), (4, "INSTALLATION > Brake hose")]
    assert page_sections(bookmarks, 7) == [
        "",  # cover and contents come before the first bookmark
        "",
        "NOTICE",
        "NOTICE",
        "INSTALLATION > Brake hose",  # the parent alone is dropped
        "INSTALLATION > Brake hose",
        "INSTALLATION > Brake hose",
    ]


def test_page_sections_names_every_section_that_starts_on_a_page() -> None:
    bookmarks = [(0, "INSTALLATION > Rotor"), (0, "INSTALLATION > Brake hose")]
    assert page_sections(bookmarks, 2) == [
        "INSTALLATION > Rotor | INSTALLATION > Brake hose",
        "INSTALLATION > Brake hose",
    ]


def test_published_reads_the_print_date_in_every_form_the_manuals_use() -> None:
    assert published("without notice. (English) © Apr. 2025 by SHIMANO INC. ITP") == "2025-04"
    assert published("March 2016 by Shimano Inc. HTR") == "2016-03"
    assert published("© May 2022 by SHIMANO INC.\nITP 14") == "2022-05"
    assert published("© Sep. 2022 by SHIMANO INC.") == "2022-09"


def test_published_is_empty_when_there_is_no_date() -> None:
    assert published("Tightening torque: 8 - 10 N·m") == ""
    assert published("Smarch 2016 by Shimano") == ""
