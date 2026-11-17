"""Our COCO annotations -> a YOLO dataset folder for training (T-201, #24).

Reads datasets/components/annotations/<bike>.json and splits.json, and writes

    data/yolo/images/{train,val}/<photo>.jpg     links to the prepared photos
    data/yolo/labels/{train,val}/<photo>.txt     one "class cx cy w h" line per box (0..1)
    data/yolo/dataset.yaml                       paths and class names

Class index = category id - 1, so index 0 is rear_derailleur and index 11 is v_brake, the
order of backend/app/vision/categories.json. Whole bikes go to a split (splits.json); test
bikes are left out, so they are never seen in training or tuning.

    python3 training/detector/prepare.py
"""

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = ROOT / "datasets" / "components"
CATEGORIES = ROOT / "backend" / "app" / "vision" / "categories.json"
OUT = ROOT / "data" / "yolo"


def main() -> None:
    categories = json.loads(CATEGORIES.read_text())["categories"]
    ids = [c["id"] for c in categories]
    if ids != list(range(1, len(ids) + 1)):
        raise SystemExit("categories.json ids must run 1..n for class index = id - 1")
    splits = json.loads((COMPONENTS / "splits.json").read_text())["bikes"]

    if OUT.exists():
        shutil.rmtree(OUT)
    counts: dict[str, list[int]] = {}
    for path in sorted((COMPONENTS / "annotations").glob("b*.json")):
        split = splits.get(path.stem)
        if split not in ("train", "val"):
            continue  # test bikes, and bikes with no split yet
        coco = json.loads(path.read_text())
        boxes: dict[int, list] = {}
        for ann in coco["annotations"]:
            boxes.setdefault(ann["image_id"], []).append(ann)
        img_dir, lbl_dir = OUT / "images" / split, OUT / "labels" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)
        n = counts.setdefault(split, [0, 0])
        for img in coco["images"]:
            src = COMPONENTS / img["file_name"]
            name = Path(img["file_name"]).name
            os.symlink(src, img_dir / name)
            w, h = img["width"], img["height"]
            lines = []
            for a in boxes.get(img["id"], []):
                x, y, bw, bh = a["bbox"]
                cx, cy = (x + bw / 2) / w, (y + bh / 2) / h
                lines.append(f"{a['category_id'] - 1} {cx:.6f} {cy:.6f} {bw / w:.6f} {bh / h:.6f}")
            (lbl_dir / name).with_suffix(".txt").write_text("\n".join(lines) + "\n" if lines else "")
            n[0] += 1
            n[1] += len(lines)

    names = "\n".join(f"  {c['id'] - 1}: {c['name']}" for c in categories)
    (OUT / "dataset.yaml").write_text(
        f"path: {OUT}\ntrain: images/train\nval: images/val\nnames:\n{names}\n"
    )
    for split, (photos, nboxes) in sorted(counts.items()):
        print(f"{split}: {photos} photos, {nboxes} boxes")
    print(f"-> {(OUT / 'dataset.yaml').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
