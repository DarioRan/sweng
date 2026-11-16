# Annotating the photograph set (T-310, #16)

We draw a box around every bike part in every photo, in COCO format, so the detector can learn from them and be tested on bikes it has never seen. All four of us annotate. **Consistency matters more than speed**: four people drawing boxes four different ways teaches the detector noise.

The class list is `backend/app/vision/categories.json`, defined in [ADR 0002](../../docs/adr/0002-component-class-list.md). The tool for every step is `annotations.py`, run from the repository root.

## What we produce

| File | What it is | In Git |
|---|---|---|
| `annotations/<bike>.json` | One COCO file per bike: every photo, every box | Yes |
| `annotations/calibration.txt` | The ten photos everyone labels first | Yes |
| `annotations/review/sample.txt`, `annotations/review/<name>.json` | The second annotator's sample and boxes | Yes |
| `splits.json` | Which bikes are train, val and test (step 6) | Yes |
| `data/labelstudio/`, `data/calibration/`, `data/review/` | Working copies, exports, review sheets | No (`data/` is ignored) |

For training, `annotations.py merge data/annotations_all.json` joins the bike files into one COCO file with each photo's split.

## Setting up (once, about 10 minutes)

1. Install the tools: `pip install label-studio pillow`
2. Start Label Studio: `label-studio start`. It opens at <http://localhost:8080>. The account you create stays on your machine.
3. Write the label config: `python3 datasets/components/annotations.py setup --list datasets/components/annotations/calibration.txt`. This also copies the calibration photos into `data/labelstudio/calibration/`.
4. In Label Studio, create a project for each batch (for example "calibration", "b01"). Under **Labeling Setup → Custom template → Code**, paste the contents of `data/labelstudio/label_config.xml`. Never type the labels by hand: the config is generated from `categories.json`, so the names always match.
5. **Data Import**: drag in the photos from `data/labelstudio/<batch>/`.

When a batch is done: **Export → COCO**, unzip, and import `result.json` as in the steps below. Only photos you have **submitted** are exported.

## The process

| Step | Who | What | Done when |
|---|---|---|---|
| 1. Guide | Narmeen | This file, the label config, the tools | Merged |
| 2. Calibration | All four | Label the same ten photos, compare, agree the rules | Every pair agrees ≥ 80% |
| 3. Annotation | One person per bike | Label every photo of the bike | `annotations/<bike>.json` merged |
| 4. Second annotator | Someone else | Label a 15% sample again, without looking | Agreement ≥ 80% |
| 5. Review | Someone else | Look at every photo with its boxes | Misses and wrong classes fixed |
| 6. Split | Team | Fix `splits.json` | `check --strict` passes |
| 7. CI | Automatic | `check` runs on every PR | Always |

### 2. Calibration

Everyone labels the ten photos in `annotations/calibration.txt`, alone and following the rules below. Each was chosen for a case the rules have to settle. Then:

```sh
python3 datasets/components/annotations.py import export.json --annotator narmeen --out data/calibration/narmeen.json
python3 datasets/components/annotations.py agree data/calibration/narmeen.json data/calibration/dario.json
```

Compare each pair. Swap the files you have so every pair is covered. `agree` lists the photos to discuss first, the parts drawn as different classes, and the boxes only one person drew. Meet for 30 minutes, settle each disagreement, and write the decision in **Decisions** at the end of this file. If a pair agrees less than 80%, do a second round with ten new photos.

### 3. Annotation, one bike at a time

Nobody annotates a bike they photographed: a fresh eye catches what the photographer took for granted.

```sh
python3 datasets/components/annotations.py setup --bike b01        # photos -> data/labelstudio/b01/
# label them in a Label Studio project "b01", export COCO, unzip
python3 datasets/components/annotations.py import result.json --annotator narmeen
python3 datasets/components/annotations.py overlay --bike b01      # review sheets -> data/review/
python3 datasets/components/annotations.py check
```

Look through the review sheets yourself, then commit `annotations/b01.json` on a branch and open a PR. If you fix boxes later, export again and import with `--force`.

### 4. Second annotator

Once at least three bikes are done, draw the sample once and commit it:

```sh
python3 datasets/components/annotations.py setup --sample 15      # writes annotations/review/sample.txt
```

A second person labels those photos **without opening the first annotations**, imports with `--out datasets/components/annotations/review/<name>.json`, and compares:

```sh
python3 datasets/components/annotations.py agree datasets/components/annotations datasets/components/annotations/review/<name>.json --min 0.8
```

Below 80%: discuss the listed photos, sharpen the rule that caused it, and fix the first annotations wherever they broke the rule.

### 5. Review

Someone who did not annotate the bike opens its review sheets (`overlay --bike b01`, or `--class chain` for one class) and checks, in this order:

1. **A part with no box.** The most harmful error: it teaches the detector that the part is background.
2. **The wrong class**, especially the look-alike pairs below.
3. **Loose or clipped boxes.**

`check` also warns when a photo has no box of its own folder's class: either the photo is in the wrong folder, or a box is missing.

### 6. Fixing the split

Whole bikes, never single photos, are put in a split: a bike's photos look alike, so splitting them would leak test photos into training.

```json
{ "bikes": { "b01": "train", "b02": "train", "b03": "train", "b10": "test" } }
```

- **test**: never used for training or for any decision. No test bike is chosen yet: they are photographed for the purpose before the first training run, so step 6 waits until then. Annotation of the training bikes does not. Between them, the test bikes need at least 10 boxes of every class; `check --strict` reports what is missing.
- **val**: one training bike set aside for tuning and early stopping, once there are at least four training bikes. Until then, the detector work (T-201) uses a random 15% of the training photos and says so.
- Once merged, a bike never changes split. New bikes can be added.

Run `python3 datasets/components/annotations.py dupes` before fixing the split: near-identical photos on different bikes would mean a mislabelled bike.

## Labelling rules

### For every photo

1. **Box every visible part of the 12 classes**, not only the part the photo was taken of. A crankset photo usually also shows the chain, a pedal and the bottom bracket.
2. **Tight boxes**: the edges touch the outermost visible pixels of the part. No shadows, no background margin.
3. **What is visible, not what you know is there.** Do not extend a box behind a frame tube to where the part probably continues. Thin things in front (spokes, cables) do not split a box.
4. **Cut off at the edge of the photo**: box the part inside the frame if you can still tell what it is.
5. **Too small or too blurred to name with confidence**: no box. As a rough guide, under 30 px on its longest side.
6. **One box per part**: two pedals are two boxes, front and rear brakes are two boxes.
7. **Not sure?** Draw your best box and post the file name and question on #16. It is settled in the next team meeting and added to **Decisions**.

### For each class

| Class | The box covers | It does not cover |
|---|---|---|
| `rear_derailleur` | Cage, both pulley wheels, body up to its mount on the hanger | Cable, cassette, chain |
| `front_derailleur` | Cage, body and its clamp or mount on the seat tube | Cable, chainrings |
| `cassette` | All the visible sprockets on the rear hub | Hub shell, spokes, derailleur |
| `chain` | One box per visible run between sprockets and chainrings; split where a tube or chain guard hides it | The chain on the teeth beyond where the run meets them |
| `crankset` | Crank arm, chainrings and spider together. The other side's arm, if visible, is its own box | Pedal, chain guard |
| `bottom_bracket` | The visible bearing cup or shell where the axle enters the frame. It may sit inside the crankset box | The crank bolt or crank arm |
| `pedal` | Pedal body, including reflectors and the axle stub | Crank arm |
| `shift_brake_lever` | One box per separate control on the bar: brake lever blade and body, trigger or grip shifter. A road dual-control lever is one box | Grip, cable, bell |
| `disc_brake_caliper` | Caliper body and its mount adapter | Rotor, hose |
| `disc_rotor` | The visible disc, also seen through the spokes | Hub, caliper |
| `rim_brake_caliper` | Both arms, centre bolt and pads of a dual-pivot caliper | Cable |
| `v_brake` | Both arms, the noodle and the pads, as one box. If only one arm is visible, that arm | Cable beyond the noodle, mudguard |

### Look-alike pairs

These are reported by name in the confusion matrix (ADR 0002). When unsure between the two, use the cue:

| Pair | Cue |
|---|---|
| `rear_derailleur` ↔ `front_derailleur` | Rear hangs below the axle with two pulley wheels; front is a cage on the seat tube above the chainrings |
| `cassette` ↔ `crankset` | Cassette is on the rear hub, with spokes around it; crankset has an arm and sits at the bottom bracket |
| `disc_rotor` ↔ `crankset` | Rotor is thin, flat, without teeth, at a hub; chainrings have teeth and a chain |
| `disc_brake_caliper` ↔ `rim_brake_caliper` | Disc caliper grips a rotor at the hub; rim caliper grips the rim at the fork crown |
| `bottom_bracket` ↔ `crankset` | Only the cup at the frame is `bottom_bracket`; everything that turns is `crankset` |
| `v_brake` ↔ `rim_brake_caliper` | V-brake: two arms on separate pivots on the fork legs, a noodle on top; caliper: one centre bolt above the tyre |

## Decisions

Settled at calibration or later. Each one is a rule from now on, and earlier annotations are fixed to match.

| Date | Question | Decision |
|---|---|---|
| | Single sprocket on a hub gear (`b01_cassette_001`): `cassette`? | To settle at calibration. ADR 0002 defines a cassette as a stack of sprockets |
| | Grip shifter next to a brake lever (`b02_shift_brake_lever_004`): one box or two? | Proposed above: two, one per separate control. To confirm |
