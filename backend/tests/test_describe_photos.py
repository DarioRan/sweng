"""Photo descriptions only fill blank rows and only accept the fixed categories (T-309).

describe_photos.py lives outside the backend package and imports the Anthropic SDK only when
run, so these tests need neither the SDK nor network access.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "describe_photos", ROOT / "datasets" / "components" / "describe_photos.py"
)
dp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dp)

ANSWER = {
    "angle": "side",
    "distance": "close",
    "occlusion": "none",
    "light": "normal",
    "shows_component": "yes",
}


def test_captures_csv_has_the_metadata_source_column() -> None:
    fields, _ = dp.read_rows()
    assert "metadata_source" in fields


def test_only_blank_rows_are_described_unless_redo() -> None:
    rows = [
        {"bike": "b01", "metadata_source": ""},
        {"bike": "b01", "metadata_source": "recipe"},
        {"bike": "b01", "metadata_source": "manual"},
        {"bike": "b02", "metadata_source": "auto:some-model"},
    ]
    assert dp.to_describe(rows, None, redo=False) == [rows[0]]
    assert dp.to_describe(rows, None, redo=True) == [rows[0], rows[3]]
    assert dp.to_describe(rows, "b02", redo=True) == [rows[3]]


def test_request_sends_the_photo_and_its_class() -> None:
    _, rows = dp.read_rows()
    req = dp.request(rows[0], "some-model")
    image, text = req["messages"][0]["content"]
    assert image["source"]["media_type"] == "image/jpeg" and image["source"]["data"]
    assert rows[0]["main_class"] in text["text"]
    assert req["output_config"]["format"]["schema"] == dp.SCHEMA


def test_answer_fills_the_row_and_records_its_source() -> None:
    row = {"angle": "", "distance": "", "occlusion": "", "light": "", "metadata_source": ""}
    dp.apply_answer(row, ANSWER, "some-model")
    assert row == {
        "angle": "side",
        "distance": "close",
        "occlusion": "none",
        "light": "normal",
        "metadata_source": "auto:some-model",
    }


def test_answer_outside_the_categories_is_rejected() -> None:
    row = {"metadata_source": ""}
    with pytest.raises(ValueError, match="angle"):
        dp.apply_answer(row, {**ANSWER, "angle": "45-left"}, "some-model")
    assert row["metadata_source"] == ""
