"""Fill in angle, distance, occlusion and light for each prepared photo (T-309, #15).

Each photo is sent to a vision model, which answers in fixed categories (defined in
CATEGORIES_TEXT below). The answers go into captures.csv, with `metadata_source` set to
"auto:<model>" so they are never mistaken for values someone checked by hand. The model is
also asked whether the photo shows its folder's part; photos where it does not are listed at
the end, to check for a wrong folder before annotation.

    pip install anthropic
    export ANTHROPIC_API_KEY=...          # or any credential the Anthropic SDK accepts
    python3 datasets/components/describe_photos.py --limit 5     # try a few first
    python3 datasets/components/describe_photos.py               # every photo still blank

Photos that already have a metadata_source are skipped: values from --recipe or filled in by
hand are never overwritten, and an interrupted run resumes where it stopped. --redo describes
the automatic ones again (for example with another --model). Progress is saved after every
photo. Each photo is one request of roughly 2,000 input tokens.
"""

import argparse
import base64
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAPTURES = HERE / "captures.csv"
DEFAULT_MODEL = "claude-opus-5-5"

ANGLES = ["side", "front", "back", "above", "below", "oblique", "unclear"]
DISTANCES = ["close", "medium", "far"]
OCCLUSIONS = ["none", "partial", "heavy"]
LIGHTS = ["normal", "bright", "dim", "flash"]
SHOWS = ["yes", "no", "unsure"]

# What each class looks like, so the model can say whether the photo shows it (ADR 0002).
CLASS_HINTS = {
    "rear_derailleur": "the cage-and-pulley mechanism hung below the rear axle",
    "front_derailleur": "the cage on the seat tube above the chainrings",
    "cassette": "the stack of sprockets on the rear hub",
    "chain": "the roller chain",
    "crankset": "the crank arms with the chainrings and spider",
    "bottom_bracket": "the bearing cups where the crank axle enters the frame",
    "pedal": "a pedal on its crank arm",
    "shift_brake_lever": "a handlebar brake lever, shifter or combined lever",
    "disc_brake_caliper": "the caliper at the hub that grips a brake disc",
    "disc_rotor": "the metal brake disc bolted to the hub",
    "rim_brake_caliper": "a dual-pivot caliper rim brake with one centre bolt",
    "v_brake": "a V-brake: two arms on separate pivots joined by a cable noodle",
}

CATEGORIES_TEXT = """\
You describe photos of bicycle components for a dataset. Each photo was taken to show one \
component, named in the request. Answer only in the categories below, judging what you see.

angle: where the camera is, relative to the bike (not to the photo)
- side: looking at the side of the bike, roughly at right angles to the frame
- front / back: looking along the bike from in front of it / from behind it
- above / below: looking down on the component / up at it
- oblique: clearly between two of these, about 45 degrees
- unclear: the bike's orientation cannot be told from the photo

distance: how much of the photo the component takes
- close: it fills most of the photo, more than about half its width or height
- medium: it is clearly visible, with some of the bike around it
- far: it is small in the photo, with much of the bike in view

occlusion: how much of the component is hidden
- none: fully visible; spokes or thin cables in front do not count
- partial: some of it is hidden behind a wheel, tube, chain guard, hand or other part
- heavy: most of it is hidden

light
- normal: even daylight or indoor light
- bright: direct sun, with strong highlights or hard shadows
- dim: shade or low light; the photo is dark or grainy
- flash: lit by the phone's flash

shows_component: does the photo show the named component at all (yes, no, unsure)?"""

SCHEMA = {
    "type": "object",
    "properties": {
        "angle": {"type": "string", "enum": ANGLES},
        "distance": {"type": "string", "enum": DISTANCES},
        "occlusion": {"type": "string", "enum": OCCLUSIONS},
        "light": {"type": "string", "enum": LIGHTS},
        "shows_component": {"type": "string", "enum": SHOWS},
    },
    "required": ["angle", "distance", "occlusion", "light", "shows_component"],
    "additionalProperties": False,
}


def read_rows() -> tuple[list[str], list[dict]]:
    with CAPTURES.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_rows(fields: list[str], rows: list[dict]) -> None:
    tmp = CAPTURES.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(CAPTURES)  # never leaves a half-written captures.csv


def to_describe(rows: list[dict], bike: str | None, redo: bool) -> list[dict]:
    """Rows still blank; with redo, also the ones described automatically before."""
    out = []
    for r in rows:
        if bike and r["bike"] != bike:
            continue
        source = r.get("metadata_source", "")
        if not source or (redo and source.startswith("auto:")):
            out.append(r)
    return out


def request(row: dict, model: str) -> dict:
    """Keyword arguments for one Messages API request about one photo."""
    data = base64.standard_b64encode((HERE / row["file_name"]).read_bytes()).decode()
    cls = row["main_class"]
    return {
        "model": model,
        "max_tokens": 4096,
        "system": CATEGORIES_TEXT,
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
                    },
                    {"type": "text", "text": f"Component: {cls} ({CLASS_HINTS.get(cls, cls)})."},
                ],
            }
        ],
    }


def apply_answer(row: dict, answer: dict, model: str) -> None:
    """Copy a validated answer into a captures.csv row."""
    allowed = {
        "angle": ANGLES,
        "distance": DISTANCES,
        "occlusion": OCCLUSIONS,
        "light": LIGHTS,
        "shows_component": SHOWS,
    }
    for key, values in allowed.items():
        if answer.get(key) not in values:
            raise ValueError(f"{key}={answer.get(key)!r} is not one of {values}")
    for key in ("angle", "distance", "occlusion", "light"):
        row[key] = answer[key]
    row["metadata_source"] = f"auto:{model}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--bike", help="only this bike, e.g. b05")
    parser.add_argument("--limit", type=int, help="describe at most this many photos")
    parser.add_argument("--redo", action="store_true", help="describe automatic ones again")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    import anthropic

    fields, rows = read_rows()
    if "metadata_source" not in fields:
        sys.exit("captures.csv has no metadata_source column: update it first (see README)")
    todo = to_describe(rows, args.bike, args.redo)[: args.limit]
    if not todo:
        print("nothing to describe")
        return
    print(f"{len(todo)} photo(s) to describe with {args.model}")

    client = anthropic.Anthropic()
    tokens_in = tokens_out = 0
    to_check: list[tuple[str, str, str]] = []
    done = 0
    for i, row in enumerate(todo, start=1):
        name = row["file_name"]
        try:
            response = client.beta.messages.create(
                **request(row, args.model),
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            sys.exit(f"credentials rejected: {e.message}")
        except anthropic.BadRequestError as e:
            print(f"[{i}/{len(todo)}] {name}: request rejected ({e.message}), skipped")
            continue
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:  # incl. 429, 5xx
            print(f"stopped at {name}: {e}. Progress is saved; run again to resume.")
            break

        tokens_in += response.usage.input_tokens
        tokens_out += response.usage.output_tokens
        if response.stop_reason == "refusal":
            print(f"[{i}/{len(todo)}] {name}: declined, left blank")
            continue
        if response.stop_reason == "max_tokens":
            print(f"[{i}/{len(todo)}] {name}: answer cut off, left blank")
            continue
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            answer = json.loads(text)
            apply_answer(row, answer, response.model)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[{i}/{len(todo)}] {name}: unusable answer ({e}), left blank")
            continue
        write_rows(fields, rows)
        done += 1
        if answer["shows_component"] != "yes":
            to_check.append((answer["shows_component"], name, row["main_class"]))
        print(
            f"[{i}/{len(todo)}] {name}: {answer['angle']}, {answer['distance']}, "
            f"{answer['occlusion']}, {answer['light']}"
        )

    print(f"\n{done} described; {tokens_in:,} input and {tokens_out:,} output tokens")
    if to_check:
        print("\nthe model did not see the folder's part in these photos (wrong folder?):")
        for shows, name, cls in to_check:
            print(f"  {shows:6s} {name}  (folder: {cls})")


if __name__ == "__main__":
    main()
