"""The frozen component class list (T-306, ADR 0002).

`categories.json` is the annotation schema: the COCO `categories` block used
for capture, annotation and training. Ids and names do not change without
amending ADR 0002, since annotations and trained weights refer to them.
"""

import json
from pathlib import Path

CATEGORIES: list[dict] = json.loads(
    (Path(__file__).with_name("categories.json")).read_text(encoding="utf-8")
)["categories"]

LABELS: tuple[str, ...] = tuple(c["name"] for c in CATEGORIES)
