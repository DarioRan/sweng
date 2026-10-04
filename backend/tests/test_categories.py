"""The annotation schema stays a valid, frozen COCO category list (T-306, ADR 0002)."""

import re

from app.vision import CATEGORIES, LABELS


def test_class_count_is_within_the_agreed_range() -> None:
    assert 10 <= len(CATEGORIES) <= 12


def test_ids_are_contiguous_from_one() -> None:
    # COCO reserves 0 for background in most trainers.
    assert [c["id"] for c in CATEGORIES] == list(range(1, len(CATEGORIES) + 1))


def test_names_are_unique_snake_case() -> None:
    assert len(set(LABELS)) == len(LABELS)
    for name in LABELS:
        assert re.fullmatch(r"[a-z]+(_[a-z]+)*", name), name


def test_every_category_has_a_known_supercategory() -> None:
    for c in CATEGORIES:
        assert c["supercategory"] in {"drivetrain", "brake", "control"}, c
