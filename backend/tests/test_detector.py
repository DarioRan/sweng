"""The detector's decoding and the /detect route (T-201, Rule 2). No weights needed."""

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.users import Role
from app.vision.detector import Box, Detector, DetectorUnavailable, decode, letterbox, load_labels

LABELS = load_labels()


def yolo_output(rows: list[tuple[float, float, float, float, int, float]]) -> np.ndarray:
    """A fake YOLO output, (1, 4 + classes, anchors): cx, cy, w, h and one class score."""
    out = np.zeros((1, 4 + len(LABELS), len(rows)), dtype=np.float32)
    for i, (cx, cy, w, h, cls, score) in enumerate(rows):
        out[0, :4, i] = (cx, cy, w, h)
        out[0, 4 + cls, i] = score
    return out


def test_labels_follow_the_class_ids() -> None:
    assert LABELS[0] == "rear_derailleur" and LABELS[11] == "v_brake" and len(LABELS) == 12


def test_letterbox_keeps_the_aspect_ratio() -> None:
    arr, scale, left, top = letterbox(Image.new("RGB", (1200, 1600)), 960)
    assert arr.shape == (1, 3, 960, 736)  # 720 wide, padded to a multiple of 32
    assert scale == pytest.approx(0.6) and top == 0 and left == 8


def test_decode_maps_boxes_back_to_the_photo_and_drops_duplicates() -> None:
    # A 1200x1600 photo letterboxed to 960: scale 0.6, 120 px of padding left and right.
    output = yolo_output(
        [
            (480, 480, 300, 300, 2, 0.9),  # cassette
            (485, 482, 300, 296, 2, 0.7),  # the same cassette again: suppressed
            (480, 480, 300, 300, 3, 0.5),  # a chain in the same place: kept, other class
            (100, 100, 50, 50, 6, 0.05),  # below the candidate floor: dropped
        ]
    )
    boxes = decode(output, LABELS, 0.6, 120, 0, 1200, 1600)
    assert [b.label for b in boxes] == ["cassette", "chain"]
    first = boxes[0]
    assert (first.x, first.y, first.width, first.height) == (350, 550, 500, 500)
    assert first.score == pytest.approx(0.9)


def test_decode_rejects_a_model_with_other_classes() -> None:
    with pytest.raises(DetectorUnavailable, match="classes"):
        decode(np.zeros((1, 4 + 3, 5), dtype=np.float32), LABELS, 1.0, 0, 0, 10, 10)


def test_missing_weights_say_how_to_get_them() -> None:
    with pytest.raises(DetectorUnavailable, match="train.py"):
        Detector("/nonexistent/detector.onnx").detect(b"")


def jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), "gray").save(buf, "JPEG")
    return buf.getvalue()


class FakeDetector:
    def __init__(self, boxes: list[Box]) -> None:
        self.boxes = boxes

    def detect(self, data: bytes):
        Image.open(io.BytesIO(data))  # as the real one: raises on a non-image
        return self.boxes, 64, 48


@pytest.fixture
def post(auth_header):
    """POST /api/detect signed in (owner by default), with the given detector behind it."""

    def send(detector, data: bytes, role: Role = Role.owner):
        with TestClient(app) as client:
            app.state.detector = detector
            try:
                return client.post(
                    "/api/detect",
                    files={"image": ("p.jpg", data)},
                    data={"job_id": "j1"},
                    headers=auth_header(role),
                )
            finally:
                del app.state.detector

    return send


def test_detect_names_the_part_only_above_the_threshold(post) -> None:
    boxes = [Box("pedal", 1, 2, 30, 20, 0.92), Box("chain", 0, 0, 9, 9, 0.3)]
    sure = post(FakeDetector(boxes), jpeg())
    assert sure.status_code == 200
    body = sure.json()
    assert body["above_threshold"] is True
    assert body["detections"][0] == {
        "label": "pedal",
        "box": {"x": 1, "y": 2, "width": 30, "height": 20},
        "score": 0.92,
    }
    unsure = post(FakeDetector([Box("pedal", 1, 2, 30, 20, 0.4)]), jpeg()).json()
    assert unsure["above_threshold"] is False and len(unsure["detections"]) == 1
    nothing = post(FakeDetector([]), jpeg()).json()
    assert nothing == {"detections": [], "above_threshold": False}


def test_detect_is_for_owners_and_technicians(post) -> None:
    assert post(FakeDetector([]), jpeg(), Role.technician).status_code == 200
    assert post(FakeDetector([]), jpeg(), Role.administrator).status_code == 403


def test_detect_explains_missing_weights_and_bad_images(post) -> None:
    assert post(Detector("/nonexistent/detector.onnx"), jpeg()).status_code == 503
    assert post(FakeDetector([]), b"not a photo").status_code == 422
