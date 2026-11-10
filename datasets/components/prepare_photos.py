"""Prepare raw phone photos for the component photograph set (T-309, #15).

Reads one bike's raw photos, sorted into one folder per class, and writes
resized copies with all metadata removed (including GPS location) to
images/<bike>/, plus one row per photo in captures.csv.

    data/raw/b01/rear_derailleur/IMG_0001.jpg ...  (raw, git-ignored)
    -> datasets/components/images/b01/b01_rear_derailleur_001.jpg

Usage, from the repository root:

    python datasets/components/prepare_photos.py data/raw/b01 --bike b01
    python datasets/components/prepare_photos.py data/raw/b04 --bike b04 --split test

Photos are taken in recipe order (shots 1-10, see README), so the shot number
fills in angle, distance, occlusion and light. Running it again skips photos
that are already prepared.
"""

import argparse
import csv
import json
import re
from pathlib import Path

from PIL import ExifTags, Image, ImageOps

HERE = Path(__file__).resolve().parent
CATEGORIES = HERE.parents[1] / "backend" / "app" / "vision" / "categories.json"
CSV_PATH = HERE / "captures.csv"
MAX_SIDE = 1600
QUALITY = 85
SUFFIXES = {".jpg", ".jpeg", ".png"}

FIELDS = [
    "file_name", "bike", "split", "main_class", "shot", "angle", "distance",
    "occlusion", "light", "device", "taken_at", "source_file", "notes",
]

# shot -> (angle, distance, occlusion, light); the 10-shot recipe in README.md
RECIPE = {
    1: ("side", "close", "none", "normal"),
    2: ("side", "far", "none", "normal"),
    3: ("front", "close", "none", "normal"),
    4: ("back", "close", "none", "normal"),
    5: ("above", "close", "none", "normal"),
    6: ("below", "close", "none", "normal"),
    7: ("45-left", "medium", "none", "normal"),
    8: ("45-right", "medium", "none", "normal"),
    9: ("any", "medium", "partial", "normal"),
    10: ("any", "close", "none", "different"),
}


def known_classes() -> set[str]:
    return {c["name"] for c in json.loads(CATEGORIES.read_text())["categories"]}


def exif_summary(img: Image.Image) -> tuple[str, str]:
    """Device and capture time, read before the metadata is dropped."""
    exif = img.getexif()
    tags = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
    device = " ".join(str(tags.get(k, "")).strip() for k in ("Make", "Model")).strip()
    taken = str(exif.get_ifd(ExifTags.IFD.Exif).get(36867, tags.get("DateTime", "")))
    return device, taken


def prepare(src: Path, dst: Path) -> tuple[str, str]:
    with Image.open(src) as img:
        device, taken = exif_summary(img)
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        # No exif= argument: the copy carries no metadata, so no GPS location.
        img.save(dst, "JPEG", quality=QUALITY, optimize=True)
    return device, taken


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("raw_dir", type=Path, help="one bike's raw folder, a subfolder per class")
    parser.add_argument("--bike", required=True, help="bike id, e.g. b01")
    parser.add_argument("--split", choices=["train", "test"], default="train")
    args = parser.parse_args()

    if not re.fullmatch(r"b\d{2}", args.bike):
        parser.error("--bike must look like b01")
    classes = known_classes()
    folders = sorted(p for p in args.raw_dir.iterdir() if p.is_dir())
    unknown = [p.name for p in folders if p.name not in classes]
    if unknown:
        parser.error(f"not a class in categories.json: {', '.join(unknown)}")

    out_dir = HERE / "images" / args.bike
    out_dir.mkdir(parents=True, exist_ok=True)
    new_file = not CSV_PATH.exists()
    rows, skipped = [], 0

    for folder in folders:
        photos = sorted(p for p in folder.iterdir() if p.suffix.lower() in SUFFIXES)
        for shot, src in enumerate(photos, start=1):
            name = f"{args.bike}_{folder.name}_{shot:03d}.jpg"
            dst = out_dir / name
            if dst.exists():
                skipped += 1
                continue
            device, taken = prepare(src, dst)
            angle, distance, occlusion, light = RECIPE.get(shot, ("", "", "", ""))
            rows.append({
                "file_name": f"images/{args.bike}/{name}", "bike": args.bike,
                "split": args.split, "main_class": folder.name, "shot": shot,
                "angle": angle, "distance": distance, "occlusion": occlusion,
                "light": light, "device": device, "taken_at": taken,
                "source_file": src.name, "notes": "",
            })

    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)

    print(f"{args.bike}: {len(rows)} prepared, {skipped} already done -> {out_dir}")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["main_class"]] = counts.get(r["main_class"], 0) + 1
    for name, n in sorted(counts.items()):
        print(f"  {name}: {n}")


if __name__ == "__main__":
    main()
