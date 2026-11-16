"""What counts as an answer page for a labelled question (calibrate.py, evaluate.py).

A question in bench/ask_questions.json lists the pages that hold its answer ('sources'),
found by reading the manuals. The torque chart repeats many values of the other manuals,
so a page the labels do not list also counts when it names the question's part and prints
every expected value. Without a part code in the question, only the listed pages count.
"""

from app.rag.retrieval import Passage
from app.rag.text import contains_value, normalise, part_codes, values


def says(text: str, wanted: str) -> bool:
    """True if `text` holds `wanted`: a value as a whole number or range, else the words."""
    found = values(wanted)
    if found:
        return all(contains_value(text, value) for value in found)
    return normalise(wanted) in normalise(text)


def says_all(text: str, must_include: list) -> bool:
    """Every expected item; a nested list means any one of its options."""
    return all(
        any(says(text, option) for option in ([item] if isinstance(item, str) else item))
        for item in must_include
    )


def listed(question: dict) -> set[tuple[str, int]]:
    return {(doc, page) for group in question.get("sources", []) for doc, page in group}


def is_source(question: dict, passage: Passage) -> bool:
    """True if the passage's page holds the answer to the question."""
    if (passage.document_id, passage.page) in listed(question):
        return True
    codes = part_codes(question["question"])
    if not codes or len(question.get("sources", [])) != 1:
        return False  # no part to anchor on, or a conflict: each side is a listed page
    folded = normalise(passage.text)
    names_part = all(code.split("-", 1)[1].lower() in folded for code in codes)
    return names_part and says_all(passage.text, question.get("must_include", []))
