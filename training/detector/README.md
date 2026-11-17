# Training the component detector (T-201, #24)

The detector behind `POST /api/detect` is a YOLO11 model fine-tuned on our photographs (`datasets/components/`), exported to ONNX and run by the backend on the CPU (`backend/app/vision/detector.py`).

## Rebuild the weights

The weights are not in Git (`*.pt` and `*.onnx` are ignored). Everything needed to rebuild them is: the photos, the annotations, the split, the settings and the seed.

```sh
python3 -m venv .venv && .venv/bin/pip install ultralytics onnx onnxslim onnxruntime pyyaml
.venv/bin/python training/detector/prepare.py       # annotations -> data/yolo/
.venv/bin/python training/detector/train.py         # ~10 min on an RTX 4000 Ada
```

`train.py` writes `models/detector.onnx`, which is what the backend loads. With `MODEL_CACHE=./models` in `.env`, the backend container sees it as `/models/detector.onnx` (the default `DETECTOR_WEIGHTS`). Restart the backend after replacing it.

Each run records its settings and validation scores in `results/<date>.md`, which is committed.

## What it is trained on

- **Train:** the bikes marked `train` in `datasets/components/splits.json`. **Val:** the bikes marked `val`, used for early stopping and the scores. **Test bikes are never read.**
- **Classes:** the twelve of `backend/app/vision/categories.json`, with class index = id - 1. `train.py` refuses a model whose class count differs.
- **Base weights:** COCO-pretrained `yolo11s.pt`. ADR 0001 also asks for a DelftBikes-pretrained run to compare. That is not done yet (T-314, #23).

## Reading the scores

The validation scores are low for now, for two known reasons:

1. **Little data.** 103 training photos, and none yet with a disc brake or a dual-pivot caliper, so those classes cannot be learnt.
2. **Missing boxes in the validation bikes.** b01 and b07 mostly have only the folder's part boxed (see the PR for T-310). A chain the detector finds correctly in a cassette photo counts as a false positive. Precision is therefore underestimated until the review fills in the boxes.

The confidence threshold of 0.6 (`DETECTOR_CONFIDENCE_THRESHOLD`) is still a placeholder, to be calibrated on the validation bikes (T-502). Below it the app never names a part. It shows candidates and search by name instead (Rule 2).
