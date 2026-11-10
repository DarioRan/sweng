# Component photograph set (T-309, #15)

Our own photos of the 11 component classes in [ADR 0002](../../docs/adr/0002-component-class-list.md), used to train and test the part detector. Target: at least 30 training photos per class, from several bikes, varied in angle, light and occlusion (ADR 0001).

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

| Bike | Type | Split | Notes |
|---|---|---|---|
| b01 | | train | |
| b02 | | train | |
| b03 | | train | |
| b04 | | test | |

### Choosing the bikes

No bike has all 11 classes: a bike has either disc brakes or rim brakes, and many MTBs have no front derailleur. Between them, the bikes must cover every class, so include at least:

- a **road bike with rim brakes**: rim brake caliper, dual control lever, front derailleur;
- a **bike with disc brakes**: disc brake caliper, disc rotor;
- a **bike with two or three chainrings**: front derailleur.

Mix road, MTB and city bikes, and 11- and 12-speed parts where possible.

## How many photos

| Per | Photos |
|---|---|
| Class, per bike | 10 (the recipe below) |
| Class, per bike, when only 2 bikes have it | 15 |
| Bike | about 80–100: only the classes it has |
| Class, in total | about 40: 30 from the training bikes, 10 from the test bike |
| Whole set | about 440 |

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
| `rim_brake_caliper` | A dual-pivot caliper at the fork crown or seatstay bridge | V-brakes and cantilevers do not count |

### Look-alike pairs: 3–5 extra shots each

These are the pairs the detector is most likely to confuse (ADR 0002). Take extra shots of both parts, after the 10 recipe shots, in the same class folders.

- `rear_derailleur` ↔ `front_derailleur`
- `cassette` ↔ `crankset`
- `disc_rotor` ↔ `crankset`
- `disc_brake_caliper` ↔ `rim_brake_caliper`
- `bottom_bracket` ↔ `crankset`

### Video sweeps

Film a slow 15-second circle around four parts: `rear_derailleur`, `crankset`, `disc_brake_caliper` and `shift_brake_lever`. Keep the videos in `data/raw/<bike>/`, outside the class folders.

## Taking the photos

For each class on each bike, take these 10 shots **in this order**. The script reads the shot number to fill in angle, distance, occlusion and light.

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

Shots after 10 (extras for look-alike pairs, or 15 per bike when only two bikes have the part) are kept but their angle columns are left blank: add a note in `captures.csv` if it matters. What counts as each part is defined in ADR 0002.

Phone settings: normal photo mode, no portrait/blur, no filters, no zoom. On an iPhone, set *Settings → Camera → Formats → Most Compatible* so photos are JPEG, not HEIC.

## After a session

1. Copy the photos from your phone into `data/raw/<bike>/`, one folder per class, named exactly as in `categories.json` (for example `data/raw/b01/rear_derailleur/`). Keep them in the order they were taken, and delete any label or failed shots: the first photo in a folder is shot 1.
2. Prepare them (needs Pillow: `pip install pillow`):

   ```sh
   python datasets/components/prepare_photos.py data/raw/b01 --bike b01
   python datasets/components/prepare_photos.py data/raw/b04 --bike b04 --split test
   ```

3. Check a few prepared photos, fill in the bike's row in the table above, then commit `images/<bike>/` and `captures.csv` on a branch and open a PR.
4. Post the count per class on #15.

To create the empty raw folders for a new bike: `python3 -c "import json,pathlib; [pathlib.Path('data/raw/b05',c['name']).mkdir(parents=True,exist_ok=True) for c in json.load(open('backend/app/vision/categories.json'))['categories']]"`

Videos (15-second sweeps around a part) stay in `data/raw/` for now; frames are extracted later and prepared the same way.
