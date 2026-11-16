"""The photograph set's annotations stay valid (T-310, datasets/components/ANNOTATION.md).

The tools live in datasets/components/annotations.py, outside the backend package, so they are
loaded by path. Nothing here needs Pillow.
"""

import csv
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "annotations", ROOT / "datasets" / "components" / "annotations.py"
)
ann = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ann)


def _photos(n: int) -> list[dict]:
    with ann.CAPTURES.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < n:
        pytest.skip("not enough photos in captures.csv")
    return rows[:n]


def _export(rows: list[dict], scale: float = 1.0) -> dict:
    """A Label Studio-style COCO export: categories 0.. by name, prefixed file names."""
    names = sorted(c["name"] for c in ann.load_categories())
    images, annotations = [], []
    for i, r in enumerate(rows):
        w, h = ann.jpeg_size(ann.HERE / r["file_name"])
        images.append(
            {
                "id": i,
                "width": round(w * scale),
                "height": round(h * scale),
                "file_name": "images\\1a2b3c4d-" + Path(r["file_name"]).name,
            }
        )
        annotations.append(
            {
                "id": i,
                "image_id": i,
                "category_id": names.index(r["main_class"]),
                "bbox": [10 * scale, 10 * scale, 100 * scale, 80 * scale],
            }
        )
    return {
        "images": images,
        "annotations": annotations,
        "categories": [{"id": k, "name": n} for k, n in enumerate(names)],
    }


def test_committed_annotations_are_valid() -> None:
    errors, _ = ann.check_all()
    assert errors == []


def test_jpeg_size_reads_every_prepared_photo() -> None:
    for r in _photos(3):
        w, h = ann.jpeg_size(ann.HERE / r["file_name"])
        assert w > 0 and h > 0 and max(w, h) <= 1600


def test_import_maps_labels_by_name_and_rescales_boxes() -> None:
    rows = _photos(2)
    parts = ann.convert(_export(rows, scale=0.5), annotator="test")
    coco = parts[rows[0]["bike"]]
    by_name = {c["name"]: c["id"] for c in ann.load_categories()}
    first = coco["annotations"][0]
    assert coco["images"][0]["file_name"] == rows[0]["file_name"]
    assert first["category_id"] == by_name[rows[0]["main_class"]]
    assert first["bbox"] == [10.0, 10.0, 100.0, 80.0]


def test_import_rejects_a_label_outside_the_class_list() -> None:
    export = _export(_photos(1))
    export["categories"][0]["name"] = "kickstand"
    with pytest.raises(ValueError, match="kickstand"):
        ann.convert(export, annotator="test")


def test_check_catches_bad_boxes_and_missing_photos() -> None:
    rows = _photos(1)
    bike = rows[0]["bike"]
    coco = ann.convert(_export(rows), annotator="test")[bike]
    assert ann.check_coco(coco, None, ann.load_captures())[0] == []

    coco["annotations"].append({**coco["annotations"][0], "id": 2, "bbox": [5, 5, 99999, 50]})
    coco["annotations"].append({**coco["annotations"][0], "id": 3, "category_id": 99})
    errors, _ = ann.check_coco(json.loads(json.dumps(coco)), bike, ann.load_captures())
    assert any("outside the photo" in e for e in errors)
    assert any("unknown category_id" in e for e in errors)
    assert any("not annotated" in e for e in errors)  # the bike's other photos


def test_agreement_counts_matches_confusions_and_misses() -> None:
    cats = ann.load_categories()
    img = [{"id": 1, "file_name": "x.jpg", "width": 100, "height": 100}]
    a = {
        "categories": cats,
        "images": img,
        "annotations": [
            {"image_id": 1, "category_id": 1, "bbox": [0, 0, 50, 50]},
            {"image_id": 1, "category_id": 2, "bbox": [60, 60, 30, 30]},
            {"image_id": 1, "category_id": 3, "bbox": [0, 60, 20, 20]},
        ],
    }
    b = {
        "categories": cats,
        "images": img,
        "annotations": [
            {"image_id": 1, "category_id": 1, "bbox": [2, 2, 50, 50]},
            {"image_id": 1, "category_id": 4, "bbox": [61, 61, 30, 30]},
        ],
    }
    r = ann.agreement(a, b)
    assert r["agreed"] == 1
    assert r["confusions"] == {"front_derailleur / chain": 1}
    assert r["only_a"] == {"cassette": 1}
    assert r["score"] == pytest.approx(2 * 1 / 5)
