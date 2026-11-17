"""The component detector behind POST /api/detect (T-201, #24).

Runs the YOLO model exported by training/detector/train.py as ONNX, on the CPU, with
onnxruntime (already installed for the embedder): no PyTorch in the backend. One photo in,
boxes with a class from categories.json and a score out.

Rule 2 (no component claimed without a detection) is applied by the caller and the client:
`detect()` returns every candidate above a low floor, best first, and the route says whether
the best one clears DETECTOR_CONFIDENCE_THRESHOLD. Below it the client shows candidates and
never names or draws one.
"""

import io
import json
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

CATEGORIES = Path(__file__).resolve().parent / "categories.json"

CANDIDATE_FLOOR = 0.15  # below this a box is noise, not a candidate worth showing
MAX_CANDIDATES = 8
NMS_IOU = 0.5


@dataclass(frozen=True)
class Box:
    label: str
    x: int
    y: int
    width: int
    height: int
    score: float


class DetectorUnavailable(RuntimeError):
    """The weights file is missing or cannot be loaded."""


def load_labels() -> list[str]:
    """Class index -> name. Index = category id - 1 (training/detector/prepare.py)."""
    categories = json.loads(CATEGORIES.read_text())["categories"]
    return [c["name"] for c in sorted(categories, key=lambda c: c["id"])]


STRIDE = 32


def letterbox(img: Image.Image, size: int) -> tuple[np.ndarray, float, int, int]:
    """Resize so the long side is `size`, keeping the aspect ratio, and pad the short side
    only up to a multiple of 32: YOLO's "rect" inference, which its validation scores use.
    (Padding to a full square changes what the model sees and measurably its answers.)"""
    scale = min(size / img.width, size / img.height)
    w, h = round(img.width * scale), round(img.height * scale)
    pw, ph = -(-w // STRIDE) * STRIDE, -(-h // STRIDE) * STRIDE
    canvas = Image.new("RGB", (pw, ph), (114, 114, 114))
    left, top = (pw - w) // 2, (ph - h) // 2
    canvas = np.asarray(canvas, dtype=np.float32).copy()
    canvas[top : top + h, left : left + w] = resize_linear(np.asarray(img, dtype=np.float32), w, h)
    arr = np.round(canvas).transpose(2, 0, 1)[None] / 255.0
    return np.ascontiguousarray(arr, dtype=np.float32), scale, left, top


def resize_linear(src: np.ndarray, w: int, h: int) -> np.ndarray:
    """Bilinear resize without antialiasing, as OpenCV's INTER_LINEAR, which YOLO trains with.

    PIL's bilinear smooths when shrinking; on our photos that moved scores by up to 0.2.
    """
    sh, sw = src.shape[:2]
    ys = np.clip((np.arange(h) + 0.5) * (sh / h) - 0.5, 0, sh - 1)
    xs = np.clip((np.arange(w) + 0.5) * (sw / w) - 0.5, 0, sw - 1)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, sh - 1), np.minimum(x0 + 1, sw - 1)
    wy, wx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    top = src[y0][:, x0] * (1 - wx) + src[y0][:, x1] * wx
    bottom = src[y1][:, x0] * (1 - wx) + src[y1][:, x1] * wx
    return top * (1 - wy) + bottom * wy


def nms(boxes: np.ndarray, scores: np.ndarray, iou: float) -> list[int]:
    """Greedy non-maximum suppression on x0, y0, x1, y1 boxes; indices kept, best first."""
    order = scores.argsort()[::-1]
    keep: list[int] = []
    area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    while order.size:
        i = order[0]
        keep.append(int(i))
        rest = order[1:]
        xx0 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy0 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx1 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy1 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(xx1 - xx0, 0, None) * np.clip(yy1 - yy0, 0, None)
        overlap = inter / (area[i] + area[rest] - inter + 1e-9)
        order = rest[overlap < iou]
    return keep


def decode(
    output: np.ndarray,
    labels: list[str],
    scale: float,
    left: int,
    top: int,
    width: int,
    height: int,
    floor: float = CANDIDATE_FLOOR,
) -> list[Box]:
    """YOLO's (1, 4 + classes, anchors) output -> boxes on the original photo, best first."""
    pred = output[0].T  # anchors x (cx, cy, w, h, class scores...)
    if pred.shape[1] != 4 + len(labels):
        raise DetectorUnavailable(
            f"model has {pred.shape[1] - 4} classes, categories.json has {len(labels)}"
        )
    cls = pred[:, 4:].argmax(1)
    score = pred[np.arange(len(pred)), 4 + cls]
    keep = score >= floor
    pred, cls, score = pred[keep], cls[keep], score[keep]
    if not len(pred):
        return []
    cx, cy, w, h = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    xyxy = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 1)
    xyxy -= np.array([left, top, left, top], dtype=np.float32)
    xyxy /= scale
    xyxy = np.clip(xyxy, 0, [width, height, width, height])

    out: list[Box] = []
    for c in np.unique(cls):  # suppress per class: a chain may lie across the crankset
        idx = np.where(cls == c)[0]
        for k in nms(xyxy[idx], score[idx], NMS_IOU):
            x0, y0, x1, y1 = xyxy[idx[k]]
            if x1 - x0 < 1 or y1 - y0 < 1:
                continue
            out.append(
                Box(
                    label=labels[int(c)],
                    x=int(round(x0)),
                    y=int(round(y0)),
                    width=int(round(x1 - x0)),
                    height=int(round(y1 - y0)),
                    score=round(float(score[idx[k]]), 4),
                )
            )
    out.sort(key=lambda b: b.score, reverse=True)
    return out[:MAX_CANDIDATES]


class Detector:
    """Loads the ONNX weights once, on first use; safe to call from worker threads."""

    def __init__(self, weights: str | Path) -> None:
        self.weights = Path(weights)
        self.labels = load_labels()
        self._session = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._session is None:
                if not self.weights.exists():
                    raise DetectorUnavailable(
                        f"no detector weights at {self.weights}: train them with "
                        "training/detector/train.py, or set DETECTOR_WEIGHTS"
                    )
                import onnxruntime as ort

                self._session = ort.InferenceSession(
                    str(self.weights), providers=["CPUExecutionProvider"]
                )
        return self._session

    @staticmethod
    def _size(session, inp) -> int:
        """Training size: fixed in the input of a static export, in the metadata otherwise."""
        if isinstance(inp.shape[2], int):
            return int(inp.shape[2])
        meta = session.get_modelmeta().custom_metadata_map.get("imgsz", "[640, 640]")
        return max(int(v) for v in meta.strip("[]").split(","))

    def detect(self, data: bytes) -> tuple[list[Box], int, int]:
        """Boxes on the photo as the user sees it (EXIF rotation applied), and its size."""
        session = self._load()
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        inp = session.get_inputs()[0]
        size = self._size(session, inp)
        arr, scale, left, top = letterbox(img, size)
        (output,) = session.run(None, {inp.name: arr})
        return decode(output, self.labels, scale, left, top, img.width, img.height), *img.size
