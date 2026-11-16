"""Train the component detector and export it for the backend (T-201, #24).

    python3 training/detector/prepare.py            # COCO annotations -> data/yolo/
    python3 training/detector/train.py              # train, evaluate on val, export

Needs `pip install ultralytics onnx onnxslim` and, for a run in minutes rather than hours,
a CUDA GPU. Settings are in config.yaml, beside this file. The run writes

    models/detector.onnx            what the backend loads (DETECTOR_WEIGHTS); git-ignored
    models/detector.pt              the PyTorch weights, to fine-tune from; git-ignored
    training/detector/results/<date>.md   the run's settings and val scores; committed

The weights are not committed (.gitignore: *.pt, *.onnx). Anyone can rebuild them with the
two commands above: the data, the split, the settings and the seed are all in the repository.
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATASET = ROOT / "data" / "yolo" / "dataset.yaml"
RUNS = ROOT / "data" / "yolo-runs"
MODELS = ROOT / "models"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", type=Path, default=HERE / "config.yaml")
    parser.add_argument("--epochs", type=int, help="override config.yaml, for a quick try")
    parser.add_argument("--device", default=None, help="e.g. 0 or cpu (default: GPU if any)")
    args = parser.parse_args()

    from ultralytics import YOLO

    if not DATASET.exists():
        sys.exit("data/yolo/dataset.yaml missing: run training/detector/prepare.py first")
    config = yaml.safe_load(args.config.read_text())
    base = config.pop("base")
    if args.epochs:
        config["epochs"] = args.epochs
    name = datetime.now().strftime("%Y%m%d-%H%M%S")

    model = YOLO(base)
    model.train(
        data=str(DATASET), project=str(RUNS), name=name, device=args.device, **config
    )
    run = RUNS / name
    best = YOLO(run / "weights" / "best.pt")
    metrics = best.val(data=str(DATASET), split="val", imgsz=config["imgsz"], device=args.device)

    MODELS.mkdir(exist_ok=True)
    shutil.copy2(run / "weights" / "best.pt", MODELS / "detector.pt")
    # dynamic: the backend pads each photo only to a multiple of 32, as YOLO validates.
    onnx = Path(best.export(format="onnx", imgsz=config["imgsz"], simplify=True, dynamic=True))
    shutil.copy2(onnx, MODELS / "detector.onnx")

    names = best.names
    lines = [
        f"# Detector run {name}",
        "",
        f"Base weights `{base}`, settings `{args.config.name}`"
        f"{f' with epochs={args.epochs}' if args.epochs else ''}. "
        "Validation bikes from `splits.json`; test bikes are not used.",
        "",
        "| Class | Precision | Recall | mAP50 | mAP50-95 |",
        "|---|---|---|---|---|",
    ]
    box = metrics.box
    for i, c in enumerate(box.ap_class_index):
        p, r, ap50, ap = box.class_result(i)
        lines.append(f"| {names[int(c)]} | {p:.2f} | {r:.2f} | {ap50:.2f} | {ap:.2f} |")
    lines += [
        f"| **all** | **{box.mp:.2f}** | **{box.mr:.2f}** | **{box.map50:.2f}** | "
        f"**{box.map:.2f}** |",
        "",
        "Classes with no box in the validation bikes are not listed: they cannot be scored.",
        "",
        "```yaml",
        args.config.read_text().strip(),
        "```",
    ]
    out = HERE / "results" / f"{name}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"\nweights -> {MODELS / 'detector.onnx'}\nscores  -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
