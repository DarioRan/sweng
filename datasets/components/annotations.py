"""Annotation tools for the component photograph set (T-310, #16).

Run from the repository root. The process is in ANNOTATION.md.

    setup   --bike b01 | --list FILE | --sample 15
                        flat copy of photos to upload to Label Studio, and its label config
    import  EXPORT.json --annotator NAME [--out FILE]
                        Label Studio COCO export -> annotations/<bike>.json (or one --out file)
    agree   A B         agreement between two annotators of the same photos (files or folders)
    check   [--strict]  validate annotations/*.json and splits.json; also run in CI
    overlay --bike b01 [--class chain] [--file F]
                        contact sheets with the boxes drawn, for review
    merge   OUT.json    one COCO file of every annotated bike, with its split, for training
    dupes               near-identical photos

Only `setup --sample`, `overlay` and `dupes` need Pillow; the rest is standard library, so the
check runs in CI without extra dependencies.
"""

import argparse
import csv
import json
import random
import re
import shutil
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CATEGORIES = ROOT / "backend" / "app" / "vision" / "categories.json"
CAPTURES = HERE / "captures.csv"
ANN_DIR = HERE / "annotations"
SPLITS = HERE / "splits.json"
WORK_DIR = ROOT / "data" / "labelstudio"  # git-ignored
REVIEW_DIR = ROOT / "data" / "review"  # git-ignored

# A prepared photo's name, also when Label Studio prefixes it ("1a2b3c4d-b01_chain_001.jpg").
NAME_RE = re.compile(r"(b\d{2})_([a-z]+(?:_[a-z]+)*)_(\d{3})\.jpg$")
IOU_MATCH = 0.5  # two boxes are the same part when they overlap at least this much
MIN_SIDE = 4  # px; smaller boxes are slips of the mouse
TEST_MIN_BOXES = 10  # per class in the test split (README: 10 photos per class from the test bike)
SPLIT_NAMES = {"train", "val", "test"}

# One colour per class id, readable on photos.
COLOURS = [
    "#e6194b",
    "#3cb44b",
    "#ffe119",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#46f0f0",
    "#f032e6",
    "#bcf60c",
    "#fabebe",
    "#008080",
    "#e6beff",
]


# ---------------------------------------------------------------- loading


def load_categories() -> list[dict]:
    return json.loads(CATEGORIES.read_text())["categories"]


def load_captures() -> dict[str, dict]:
    """Prepared photos by base name, from captures.csv."""
    with CAPTURES.open(newline="", encoding="utf-8") as f:
        return {Path(r["file_name"]).name: r for r in csv.DictReader(f)}


def jpeg_size(path: Path) -> tuple[int, int]:
    """Width and height read from the JPEG frame header (no Pillow needed)."""
    with path.open("rb") as f:
        if f.read(2) != b"\xff\xd8":
            raise ValueError(f"{path}: not a JPEG")
        while True:
            byte = f.read(1)
            if not byte:
                raise ValueError(f"{path}: no frame header")
            if byte != b"\xff":
                continue
            marker = f.read(1)[0]
            if marker == 0xFF or marker == 0x01 or 0xD0 <= marker <= 0xD8:
                if marker == 0xFF:
                    f.seek(-1, 1)
                continue
            length = int.from_bytes(f.read(2), "big")
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                f.read(1)  # sample precision
                height = int.from_bytes(f.read(2), "big")
                width = int.from_bytes(f.read(2), "big")
                return width, height
            f.seek(length - 2, 1)


def load_coco(path: Path) -> dict:
    """One annotation file, or every *.json directly inside a folder, as one COCO dict."""
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    merged: dict = {"images": [], "annotations": []}
    for file in files:
        coco = json.loads(file.read_text())
        merged.setdefault("categories", coco["categories"])
        offset = len(merged["images"])
        ids = {img["id"]: offset + i + 1 for i, img in enumerate(coco["images"])}
        for img in coco["images"]:
            merged["images"].append({**img, "id": ids[img["id"]]})
        for ann in coco["annotations"]:
            merged["annotations"].append({**ann, "image_id": ids[ann["image_id"]]})
    return merged


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- setup


def label_config(categories: list[dict]) -> str:
    labels = "\n".join(
        f'    <Label value="{c["name"]}" background="{COLOURS[(c["id"] - 1) % len(COLOURS)]}"/>'
        for c in categories
    )
    return (
        "<View>\n"
        '  <Image name="image" value="$image" zoom="true" zoomControl="true"/>\n'
        '  <RectangleLabels name="label" toName="image" strokeWidth="2">\n'
        f"{labels}\n"
        "  </RectangleLabels>\n"
        "</View>\n"
    )


def sample_photos(percent: float, seed: int) -> list[str]:
    """A random share of every bike's photos, for the second annotator."""
    rng = random.Random(seed)
    by_bike: dict[str, list[str]] = {}
    for row in load_captures().values():
        by_bike.setdefault(row["bike"], []).append(row["file_name"])
    chosen = []
    for bike in sorted(by_bike):
        files = sorted(by_bike[bike])
        chosen += sorted(rng.sample(files, max(1, round(len(files) * percent / 100))))
    return chosen


def cmd_setup(args: argparse.Namespace) -> None:
    captures = load_captures()
    if args.bike:
        files = sorted(r["file_name"] for r in captures.values() if r["bike"] == args.bike)
        name = args.bike
    elif args.list:
        files = [
            line.strip()
            for line in args.list.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        name = args.list.stem
    else:
        files = sample_photos(args.sample, args.seed)
        name = "sample"
        listing = ANN_DIR / "review" / "sample.txt"
        listing.parent.mkdir(parents=True, exist_ok=True)
        listing.write_text(
            f"# {args.sample:g}% of every bike's photos, seed {args.seed}: second annotator\n"
            + "\n".join(files)
            + "\n"
        )
        print(f"sample list written to {listing.relative_to(ROOT)}")
    if not files:
        sys.exit("no photos found")
    missing = [f for f in files if not (HERE / f).exists()]
    if missing:
        sys.exit("not found: " + ", ".join(missing))

    out = WORK_DIR / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for f in files:
        shutil.copy2(HERE / f, out / Path(f).name)
    (WORK_DIR / "label_config.xml").write_text(label_config(load_categories()))
    print(f"{len(files)} photos copied to {out.relative_to(ROOT)}")
    print(f"label config: {(WORK_DIR / 'label_config.xml').relative_to(ROOT)}")


# ---------------------------------------------------------------- import


def convert(export: dict, annotator: str) -> dict[str, dict]:
    """A Label Studio COCO export -> our COCO, one dict per bike.

    Label Studio numbers categories 0.. in its own order, so they are matched by name.
    Photos are matched by their prepared file name, whatever prefix the tool added.
    """
    categories = load_categories()
    by_name = {c["name"]: c["id"] for c in categories}
    captures = load_captures()

    cat_map = {}
    for c in export["categories"]:
        if c["name"] not in by_name:
            raise ValueError(f"label {c['name']!r} is not in categories.json")
        cat_map[c["id"]] = by_name[c["name"]]

    images, seen = {}, set()
    for img in export["images"]:
        m = NAME_RE.search(img["file_name"].replace("\\", "/"))
        if not m or m.group(0) not in captures:
            raise ValueError(f"{img['file_name']}: not a photo in captures.csv")
        base = m.group(0)
        if base in seen:
            raise ValueError(f"{base} appears twice in the export")
        seen.add(base)
        row = captures[base]
        width, height = jpeg_size(HERE / row["file_name"])
        images[img["id"]] = {
            "file_name": row["file_name"],
            "bike": row["bike"],
            "width": width,
            "height": height,
            "sx": width / img["width"],
            "sy": height / img["height"],
            "boxes": [],
        }

    for ann in export["annotations"]:
        img = images[ann["image_id"]]
        x, y, w, h = ann["bbox"]
        x0, y0 = max(0.0, x * img["sx"]), max(0.0, y * img["sy"])
        x1 = min(float(img["width"]), (x + w) * img["sx"])
        y1 = min(float(img["height"]), (y + h) * img["sy"])
        if x1 - x0 < MIN_SIDE or y1 - y0 < MIN_SIDE:
            print(f"  dropped a {x1 - x0:.0f}x{y1 - y0:.0f} px box on {img['file_name']}")
            continue
        img["boxes"].append((cat_map[ann["category_id"]], x0, y0, x1, y1))

    out: dict[str, dict] = {}
    for img in sorted(images.values(), key=lambda i: i["file_name"]):
        coco = out.setdefault(
            img["bike"],
            {
                "info": {
                    "bike": img["bike"],
                    "annotator": annotator,
                    "tool": "Label Studio",
                    "imported": date.today().isoformat(),
                },
                "categories": categories,
                "images": [],
                "annotations": [],
            },
        )
        image_id = len(coco["images"]) + 1
        coco["images"].append(
            {
                "id": image_id,
                "file_name": img["file_name"],
                "width": img["width"],
                "height": img["height"],
            }
        )
        for cat, x0, y0, x1, y1 in img["boxes"]:
            w, h = round(x1 - x0, 1), round(y1 - y0, 1)
            coco["annotations"].append(
                {
                    "id": len(coco["annotations"]) + 1,
                    "image_id": image_id,
                    "category_id": cat,
                    "bbox": [round(x0, 1), round(y0, 1), w, h],
                    "area": round(w * h, 1),
                    "iscrowd": 0,
                }
            )
    return out


def combine(parts: dict[str, dict]) -> dict:
    """Per-bike dicts from convert() as one dict (calibration and review files)."""
    first = next(iter(parts.values()))
    coco = {
        "info": {**first["info"], "bike": None},
        "categories": first["categories"],
        "images": [],
        "annotations": [],
    }
    for bike in sorted(parts):
        part = parts[bike]
        offset = len(coco["images"])
        for img in part["images"]:
            coco["images"].append({**img, "id": img["id"] + offset})
        for ann in part["annotations"]:
            coco["annotations"].append(
                {**ann, "id": len(coco["annotations"]) + 1, "image_id": ann["image_id"] + offset}
            )
    return coco


def cmd_import(args: argparse.Namespace) -> None:
    parts = convert(json.loads(args.export.read_text()), args.annotator)
    if not parts:
        sys.exit("the export has no photos")
    if args.out:
        write_json(args.out, combine(parts))
        n = sum(len(p["images"]) for p in parts.values())
        print(f"{n} photos -> {args.out}")
        return
    captures = load_captures()
    for bike, coco in sorted(parts.items()):
        path = ANN_DIR / f"{bike}.json"
        if path.exists() and not args.force:
            sys.exit(f"{path.relative_to(ROOT)} exists: pass --force to replace it")
        expected = {r["file_name"] for r in captures.values() if r["bike"] == bike}
        missing = sorted(expected - {i["file_name"] for i in coco["images"]})
        write_json(path, coco)
        print(
            f"{bike}: {len(coco['images'])} photos, {len(coco['annotations'])} boxes "
            f"-> {path.relative_to(ROOT)}"
        )
        for f in missing:
            print(f"  not in the export (not submitted?): {f}")


# ---------------------------------------------------------------- agreement


def iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, bx1, by1 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw = max(0.0, min(ax1, bx1) - max(a[0], b[0]))
    ih = max(0.0, min(ay1, by1) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union else 0.0


def agreement(a: dict, b: dict) -> dict:
    """Match the boxes of two annotators on the photos both labelled.

    Boxes are paired greedily by overlap (IoU >= 0.5), whatever their class. A pair with the
    same class agrees; a pair with different classes is a confusion; a box with no pair is a
    miss by the other annotator. Score = 2 * agreed / (boxes in A + boxes in B).
    """
    names = {c["id"]: c["name"] for c in a["categories"]}

    def boxes(coco: dict) -> dict[str, list]:
        by_id = {img["id"]: img["file_name"] for img in coco["images"]}
        out: dict[str, list] = {f: [] for f in by_id.values()}
        for ann in coco["annotations"]:
            out[by_id[ann["image_id"]]].append((ann["category_id"], ann["bbox"]))
        return out

    ba, bb = boxes(a), boxes(b)
    common = sorted(set(ba) & set(bb))
    result = {
        "photos": len(common),
        "agreed": 0,
        "boxes_a": 0,
        "boxes_b": 0,
        "confusions": {},
        "only_a": {},
        "only_b": {},
        "per_class": {},
        "per_photo": [],
    }

    def count(d: dict, key: str) -> None:
        d[key] = d.get(key, 0) + 1

    for f in common:
        la, lb = ba[f], bb[f]
        result["boxes_a"] += len(la)
        result["boxes_b"] += len(lb)
        pairs = sorted(
            ((iou(x[1], y[1]), i, j) for i, x in enumerate(la) for j, y in enumerate(lb)),
            reverse=True,
        )
        used_a, used_b, agreed = set(), set(), 0
        for score, i, j in pairs:
            if score < IOU_MATCH or i in used_a or j in used_b:
                continue
            used_a.add(i)
            used_b.add(j)
            ca, cb = names[la[i][0]], names[lb[j][0]]
            if ca == cb:
                agreed += 1
                count(result["per_class"], ca)
            else:
                count(result["confusions"], f"{ca} / {cb}")
        for i, (cat, _) in enumerate(la):
            if i not in used_a:
                count(result["only_a"], names[cat])
        for j, (cat, _) in enumerate(lb):
            if j not in used_b:
                count(result["only_b"], names[cat])
        result["agreed"] += agreed
        total = len(la) + len(lb)
        result["per_photo"].append((2 * agreed / total if total else 1.0, f))

    total = result["boxes_a"] + result["boxes_b"]
    result["score"] = 2 * result["agreed"] / total if total else 1.0
    result["per_photo"].sort()
    return result


def cmd_agree(args: argparse.Namespace) -> None:
    r = agreement(load_coco(args.a), load_coco(args.b))
    if not r["photos"]:
        sys.exit("no photo is in both")
    print(f"{r['photos']} photos in both; boxes: {r['boxes_a']} in A, {r['boxes_b']} in B")
    print(f"agreement: {r['score']:.0%} ({r['agreed']} boxes agreed, IoU >= {IOU_MATCH})")
    for title, key in [
        ("same part, different class (A / B)", "confusions"),
        ("only A drew", "only_a"),
        ("only B drew", "only_b"),
    ]:
        if r[key]:
            print(f"\n{title}:")
            for k, n in sorted(r[key].items(), key=lambda kv: -kv[1]):
                print(f"  {n:3d}  {k}")
    worst = [(score, f) for score, f in r["per_photo"][:10] if score < 1]
    if worst:
        print("\nphotos to discuss first:")
        for score, f in worst:
            print(f"  {score:4.0%}  {f}")
    if args.min is not None and r["score"] < args.min:
        sys.exit(f"\nbelow the agreed minimum of {args.min:.0%}: recalibrate (ANNOTATION.md)")


# ---------------------------------------------------------------- check


def check_coco(coco: dict, bike: str | None, captures: dict[str, dict]) -> tuple[list, list]:
    """Errors and warnings for one annotation file."""
    errors, warnings = [], []
    categories = load_categories()
    cat_ids = {c["id"]: c["name"] for c in categories}
    if coco.get("categories") != categories:
        errors.append("categories differ from backend/app/vision/categories.json")

    by_file = {Path(r["file_name"]).name: r for r in captures.values()}
    image_ids, files = set(), set()
    for img in coco.get("images", []):
        f = img.get("file_name", "")
        base = Path(f).name
        if img["id"] in image_ids:
            errors.append(f"image id {img['id']} used twice")
        image_ids.add(img["id"])
        if base not in by_file or by_file[base]["file_name"] != f:
            errors.append(f"{f}: not a photo in captures.csv")
            continue
        if f in files:
            errors.append(f"{f}: listed twice")
        files.add(f)
        if bike and by_file[base]["bike"] != bike:
            errors.append(f"{f}: belongs to {by_file[base]['bike']}, not {bike}")
        path = HERE / f
        if not path.exists():
            errors.append(f"{f}: file missing")
        elif jpeg_size(path) != (img.get("width"), img.get("height")):
            errors.append(f"{f}: width/height do not match the photo")

    sizes = {
        img["id"]: (img.get("width", 0), img.get("height", 0), img.get("file_name"))
        for img in coco.get("images", [])
    }
    ann_ids, boxed, main_boxed = set(), set(), set()
    for ann in coco.get("annotations", []):
        where = f"annotation {ann.get('id')}"
        if ann.get("id") in ann_ids:
            errors.append(f"{where}: id used twice")
        ann_ids.add(ann.get("id"))
        if ann.get("image_id") not in sizes:
            errors.append(f"{where}: unknown image_id")
            continue
        w_img, h_img, f = sizes[ann["image_id"]]
        where = f"{f}, annotation {ann.get('id')}"
        if ann.get("category_id") not in cat_ids:
            errors.append(f"{where}: unknown category_id {ann.get('category_id')}")
            continue
        bbox = ann.get("bbox", [])
        if len(bbox) != 4:
            errors.append(f"{where}: bbox must be [x, y, width, height]")
            continue
        x, y, w, h = bbox
        if w < MIN_SIDE or h < MIN_SIDE:
            errors.append(f"{where}: box smaller than {MIN_SIDE} px")
        if x < -0.5 or y < -0.5 or x + w > w_img + 0.5 or y + h > h_img + 0.5:
            errors.append(f"{where}: box outside the photo")
        boxed.add(ann["image_id"])
        if f and cat_ids[ann["category_id"]] == by_file.get(Path(f).name, {}).get("main_class"):
            main_boxed.add(ann["image_id"])

    for image_id, (_, _, f) in sizes.items():
        if image_id not in boxed:
            errors.append(f"{f}: no boxes (every photo shows at least its folder's part)")
        elif image_id not in main_boxed:
            warnings.append(f"{f}: no box of its folder's class: misfiled, or a box missing?")

    if bike:
        expected = {r["file_name"] for r in captures.values() if r["bike"] == bike}
        for f in sorted(expected - files):
            errors.append(f"{f}: photo of {bike} not annotated")
    return errors, warnings


def check_all(strict: bool = False) -> tuple[list[str], list[str]]:
    """Every annotations/<bike>.json, splits.json, and the test split's class coverage."""
    errors, warnings = [], []
    captures = load_captures()
    files = sorted(ANN_DIR.glob("*.json"))
    for path in files:
        if not re.fullmatch(r"b\d{2}", path.stem):
            errors.append(f"{path.name}: annotation files are named after the bike, e.g. b01.json")
            continue
        e, w = check_coco(json.loads(path.read_text()), path.stem, captures)
        errors += [f"{path.name}: {m}" for m in e]
        warnings += [f"{path.name}: {m}" for m in w]

    if SPLITS.exists():
        splits = json.loads(SPLITS.read_text()).get("bikes", {})
        for bike, split in splits.items():
            if split not in SPLIT_NAMES:
                errors.append(f"splits.json: {bike} has split {split!r}")
        for path in files:
            if path.stem not in splits:
                errors.append(f"splits.json: annotated bike {path.stem} has no split")
        for r in captures.values():
            if r["split"] == "test" and splits.get(r["bike"]) not in (None, "test"):
                errors.append(f"splits.json: {r['bike']} is test in captures.csv")
                break
        test_counts: dict[str, int] = {}
        for path in files:
            if splits.get(path.stem) == "test":
                for ann in json.loads(path.read_text())["annotations"]:
                    test_counts[ann["category_id"]] = test_counts.get(ann["category_id"], 0) + 1
        thin = [
            f"{c['name']} ({test_counts.get(c['id'], 0)})"
            for c in load_categories()
            if test_counts.get(c["id"], 0) < TEST_MIN_BOXES
        ]
        if thin:
            msg = f"test split has fewer than {TEST_MIN_BOXES} boxes of: {', '.join(thin)}"
            (errors if strict else warnings).append(msg)
    elif strict:
        errors.append("splits.json missing")
    return errors, warnings


def cmd_check(args: argparse.Namespace) -> None:
    errors, warnings = check_all(args.strict)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    n = len(list(ANN_DIR.glob("*.json")))
    print(f"{n} annotation file(s): {len(errors)} error(s), {len(warnings)} warning(s)")
    if errors:
        sys.exit(1)


# ---------------------------------------------------------------- overlay


def cmd_overlay(args: argparse.Namespace) -> None:
    from PIL import Image, ImageDraw, ImageOps

    path = args.file or ANN_DIR / f"{args.bike}.json"
    coco = load_coco(path)
    names = {c["id"]: c["name"] for c in coco["categories"]}
    images = [
        i
        for i in coco["images"]
        if (not args.bike or f"/{args.bike}/" in i["file_name"])
        and (not args.cls or f"/{args.cls}/" in i["file_name"])
    ]
    if not images:
        sys.exit("no photos match")
    boxes: dict[int, list] = {}
    for ann in coco["annotations"]:
        boxes.setdefault(ann["image_id"], []).append(ann)

    side, cols, per_sheet = 480, 4, 16
    tag = "_".join(x for x in [args.bike or path.stem, args.cls] if x)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(images), per_sheet):
        chunk = images[start : start + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * side, rows * (side + 20)), "white")
        draw = ImageDraw.Draw(sheet)
        for k, img in enumerate(chunk):
            photo = ImageOps.exif_transpose(Image.open(HERE / img["file_name"])).convert("RGB")
            scale = side / max(photo.size)
            photo = photo.resize((round(photo.width * scale), round(photo.height * scale)))
            pd = ImageDraw.Draw(photo)
            for ann in boxes.get(img["id"], []):
                x, y, w, h = (v * scale for v in ann["bbox"])
                colour = COLOURS[(ann["category_id"] - 1) % len(COLOURS)]
                pd.rectangle([x, y, x + w, y + h], outline=colour, width=3)
                label = names[ann["category_id"]]
                pd.rectangle([x, y, x + 7 * len(label), y + 12], fill=colour)
                pd.text((x + 2, y), label, fill="black")
            cx, cy = (k % cols) * side, (k // cols) * (side + 20)
            sheet.paste(photo, (cx, cy + 20))
            draw.text((cx + 4, cy + 4), Path(img["file_name"]).name, fill="black")
        out = REVIEW_DIR / f"{tag}_{start // per_sheet + 1}.jpg"
        sheet.save(out, quality=85)
        print(out.relative_to(ROOT))


# ---------------------------------------------------------------- merge


def cmd_merge(args: argparse.Namespace) -> None:
    errors, _ = check_all()
    if errors:
        sys.exit("fix `check` errors first")
    if not SPLITS.exists():
        sys.exit("splits.json missing: the split is fixed before training (ANNOTATION.md)")
    splits = json.loads(SPLITS.read_text())["bikes"]
    out = {
        "info": {
            "description": "Component photograph set (T-309/T-310)",
            "date_created": date.today().isoformat(),
        },
        "categories": load_categories(),
        "images": [],
        "annotations": [],
    }
    for path in sorted(ANN_DIR.glob("*.json")):
        coco = json.loads(path.read_text())
        ids = {}
        for img in coco["images"]:
            ids[img["id"]] = len(out["images"]) + 1
            out["images"].append(
                {
                    **img,
                    "id": ids[img["id"]],
                    "bike": path.stem,
                    "split": splits[path.stem],
                    "annotator": coco["info"].get("annotator"),
                }
            )
        for ann in coco["annotations"]:
            out["annotations"].append(
                {**ann, "id": len(out["annotations"]) + 1, "image_id": ids[ann["image_id"]]}
            )
    write_json(args.out, out)
    counts: dict[str, int] = {}
    for img in out["images"]:
        counts[img["split"]] = counts.get(img["split"], 0) + 1
    print(f"{len(out['images'])} photos, {len(out['annotations'])} boxes -> {args.out}: {counts}")


# ---------------------------------------------------------------- duplicates


def dhash(path: Path) -> int:
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(path)).convert("L").resize((9, 8))
    px = img.tobytes()
    return sum(1 << i for i in range(64) if px[(i // 8) * 9 + i % 8] > px[(i // 8) * 9 + i % 8 + 1])


def cmd_dupes(args: argparse.Namespace) -> None:
    rows = sorted(load_captures().values(), key=lambda r: r["file_name"])
    hashes = [(r, dhash(HERE / r["file_name"])) for r in rows]
    found = 0
    for i, (ra, ha) in enumerate(hashes):
        for rb, hb in hashes[i + 1 :]:
            d = (ha ^ hb).bit_count()
            if d <= args.max_distance:
                found += 1
                flag = "  <- different bikes" if ra["bike"] != rb["bike"] else ""
                print(f"{d:2d}  {ra['file_name']}  {rb['file_name']}{flag}")
    print(f"{found} near-identical pair(s) among {len(rows)} photos")


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("setup", help="copy photos for Label Studio and write its label config")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--bike")
    g.add_argument("--list", type=Path, help="text file, one photo file_name per line")
    g.add_argument("--sample", type=float, help="percent of every bike, for the second annotator")
    p.add_argument("--seed", type=int, default=16)
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("import", help="Label Studio COCO export -> annotations/<bike>.json")
    p.add_argument("export", type=Path)
    p.add_argument("--annotator", required=True)
    p.add_argument("--out", type=Path, help="write one file instead (calibration, review)")
    p.add_argument("--force", action="store_true", help="replace existing bike files")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("agree", help="agreement between two annotators")
    p.add_argument("a", type=Path)
    p.add_argument("b", type=Path)
    p.add_argument("--min", type=float, help="fail below this score, e.g. 0.8")
    p.set_defaults(func=cmd_agree)

    p = sub.add_parser("check", help="validate the annotation files (CI)")
    p.add_argument("--strict", action="store_true", help="also require the final test split")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("overlay", help="contact sheets with boxes, for review")
    p.add_argument("--bike")
    p.add_argument("--class", dest="cls")
    p.add_argument("--file", type=Path, help="annotation file or folder (default: the bike's)")
    p.set_defaults(func=cmd_overlay)

    p = sub.add_parser("merge", help="one COCO file of all bikes, for training")
    p.add_argument("out", type=Path)
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("dupes", help="near-identical photos")
    p.add_argument("--max-distance", type=int, default=4, help="bits of 64 that may differ")
    p.set_defaults(func=cmd_dupes)

    args = parser.parse_args()
    if args.command == "overlay" and not (args.bike or args.file):
        parser.error("overlay needs --bike or --file")
    args.func(args)


if __name__ == "__main__":
    main()
