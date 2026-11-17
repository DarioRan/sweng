# Component photograph set (T-309, #15)

Our own photos of the 12 component classes in [ADR 0002](../../docs/adr/0002-component-class-list.md), used to train and test the part detector. Target: at least 30 training photos per class, from several bikes, varied in angle, light and occlusion (ADR 0001).

**This repository is public.** Everything in this folder can be seen by anyone. So:

- Only photos you took yourself, of bikes whose owners agreed.
- No faces, number plates or house numbers in the frame.
- Never commit raw phone photos: they carry the GPS location where they were taken. Always go through `prepare_photos.py`, which removes it.

## Layout

```
data/raw/<bike>/<class>/*.jpg          raw phone photos — git-ignored, stay on your machine
datasets/components/
  images/<bike>/<class>/<bike>_<class>_NNN.jpg   prepared photos: max 1600 px, no metadata
  captures.csv                          one row per photo (written by the script)
  prepare_photos.py                     raw -> prepared
```

Bike ids are `b01`, `b02`, … in the order bikes are photographed. **Whole bikes are held out for testing**: every photo of a test bike has `split = test` and is never used for training or tuning. Photos of the same bike in both training and test would make the detector look better than it is.

**No test bike is chosen yet.** b01 and b07 are the validation bikes (`splits.json`), used for tuning and early stopping; the others are training bikes. The test bikes are photographed later, for that purpose, before the detector is first trained (T-201). Between them they need about 10 photos of every class, so look for bikes with many of the classes, including disc brakes and dual-pivot calipers.

| Bike | Type | Split | Notes |
|---|---|---|---|
| b01 | City bike, chain guard, hub gear, V-brakes | val | |
| b02 | Full-suspension MTB, 3×7 speed, V-brakes | train | |
| b03 | TBM city e-bike (Bordeaux shared bike) | train | |
| b04 | Photographed 16 Nov in a bike rack | train | Photos may come from more than one bike: to regroup |
| b05 | Photographed 16 Nov in a bike rack | train | |
| b06 | Photographed 16 Nov in a bike rack | train | The two photos may be two bikes: to regroup |
| b07 | White frame, SRAM rear derailleur, Shimano Tourney front derailleur | val | |

### Choosing the bikes

No bike has all 12 classes: a bike has one kind of brake (disc, dual-pivot caliper or V-brake), and many MTBs have no front derailleur. Between them, the bikes must cover every class, so include at least:

- a **road bike with drop bars**: dual-pivot rim brake caliper, dual control lever, front derailleur;
- a **city, hybrid or older MTB with V-brakes**;
- a **bike with disc brakes**: disc brake caliper, disc rotor;
- a **bike with two or three chainrings**: front derailleur.

Mix road, MTB and city bikes, and 11- and 12-speed parts where possible.

## How many photos

| Per | Photos |
|---|---|
| Class, per bike | 10 (the recipe below) |
| Class, per bike, when only 2 bikes have it | 15 |
| Bike | about 80–100: only the classes it has |
| Class, in total | about 40: 30 from the training bikes, 10 from the test bikes |
| Whole set | about 480 |

## The classes: what each photo must show

Sort each photo into the folder of the part it mainly shows. Other parts in the background are fine: every visible part gets a box at annotation (#16). Full definitions are in ADR 0002.

| Folder | Must be in the photo | Watch out for |
|---|---|---|
| `rear_derailleur` | The cage and both pulley wheels, hung from the rear dropout | Shift gears between shots: the cage position changes |
| `front_derailleur` | The cage on the seat tube, above the chainrings | Only on bikes with 2–3 chainrings |
| `cassette` | The whole sprocket stack on the rear hub | Shoot from behind the wheel and from the side; one shot with the wheel removed is a good extra |
| `chain` | A visible run of chain | Top and bottom runs; some close-ups of links |
| `crankset` | Crank arm with chainrings and spider | Pedals are not part of it. Include the non-drive-side arm too |
| `bottom_bracket` | The bearing cups where the cranks enter the frame | Usually hidden behind the crank: shots 5 and 6 (above, below) matter most |
| `pedal` | The pedal body on its crank arm | Flat and clipless if possible; top, side and underneath |
| `shift_brake_lever` | A handlebar lever that brakes, shifts or both | Road dual control levers, MTB brake levers and trigger shifters all count. Add a rider's-eye view from behind the bars |
| `disc_brake_caliper` | The caliper on the fork or frame mount | Front and rear; include the rotor where it is visible |
| `disc_rotor` | The metal disc bolted to the hub | The full disc and a close-up; one shot through the spokes |
| `rim_brake_caliper` | A dual-pivot caliper, held by one bolt at the fork crown or seatstay bridge | Road bikes with drop bars. V-brakes go in `v_brake`; cantilevers do not count |
| `v_brake` | Both arms, each on its own pivot on the fork legs or seatstays, and the cable noodle across the top | City, hybrid and older MTBs. Shoot front and rear brake; include a front view showing both pivots |

### Look-alike pairs: 3–5 extra shots each

These are the pairs the detector is most likely to confuse (ADR 0002). Take extra shots of both parts, after the 10 recipe shots, in the same class folders.

- `rear_derailleur` ↔ `front_derailleur`
- `cassette` ↔ `crankset`
- `disc_rotor` ↔ `crankset`
- `disc_brake_caliper` ↔ `rim_brake_caliper`
- `v_brake` ↔ `rim_brake_caliper`
- `bottom_bracket` ↔ `crankset`

### Video sweeps

Film a slow 15-second circle around four parts: `rear_derailleur`, `crankset`, `disc_brake_caliper` and `shift_brake_lever`. Keep the videos in `data/raw/<bike>/`, outside the class folders.

## Taking the photos

For each class on each bike, aim for these 10 shots. They are a checklist for variety, not a fixed order: angle, distance, occlusion and light are filled in afterwards from the photos themselves (step 3 below).

| Shot | Angle | Distance | Notes |
|---|---|---|---|
| 1 | Side, straight on | Close (20–30 cm) | Part fills most of the frame |
| 2 | Side | Far (60–80 cm) | Some of the bike around it |
| 3 | Front | Close | |
| 4 | Back | Close | |
| 5 | From above | Close | |
| 6 | From below | Close | |
| 7 | 45° from the left | Medium (40 cm) | |
| 8 | 45° from the right | Medium | |
| 9 | Any | Medium | **Partly hidden**: behind a wheel, cable, frame tube or hand |
| 10 | Any | Close | **Different light**: flash, shade or a dim spot |

Extra shots (for look-alike pairs, or 15 per bike when only two bikes have the part) are welcome. What counts as each part is defined in ADR 0002.

Phone settings: normal photo mode, no portrait/blur, no filters, no zoom. On an iPhone, set *Settings → Camera → Formats → Most Compatible* so photos are JPEG, not HEIC.

## After a session

1. Copy the photos from your phone into `data/raw/<bike>/`, one folder per class, named exactly as in `categories.json` (for example `data/raw/b01/rear_derailleur/`). Keep them in the order they were taken, and delete any label or failed shots: the first photo in a folder is shot 1.
2. Prepare them (needs Pillow: `pip install pillow`):

   ```sh
   python datasets/components/prepare_photos.py data/raw/b01 --bike b01
   python datasets/components/prepare_photos.py data/raw/b10 --bike b10 --split test   # a test bike
   ```

3. Fill in angle, distance, occlusion and light (needs an Anthropic API key: `pip install anthropic`, then `export ANTHROPIC_API_KEY=...`):

   ```sh
   python3 datasets/components/describe_photos.py --bike b01
   ```

   A vision model looks at each photo and answers in fixed categories (defined at the top of the script); `metadata_source` records which model answered. It also lists photos where it could not see the folder's part: check those for a wrong folder. Each photo costs one request of about 2,000 input tokens. Values in a row whose `metadata_source` is set are never overwritten, so a value corrected by hand stays: set its `metadata_source` to `manual`.
4. Check a few prepared photos, fill in the bike's row in the table above, then commit `images/<bike>/` and `captures.csv` on a branch and open a PR.
5. Post the count per class on #15.

To create the empty raw folders for a new bike: `python3 -c "import json,pathlib; [pathlib.Path('data/raw/b05',c['name']).mkdir(parents=True,exist_ok=True) for c in json.load(open('backend/app/vision/categories.json'))['categories']]"`

Videos (15-second sweeps around a part) stay in `data/raw/` for now; frames are extracted later and prepared the same way.

## Annotation

Boxes are drawn in Label Studio and stored as one COCO file per bike in `annotations/`. The rules and the step-by-step process are in [ANNOTATION.md](ANNOTATION.md).
