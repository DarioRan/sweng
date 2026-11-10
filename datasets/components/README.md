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
  images/<bike>/<bike>_<class>_NNN.jpg  prepared photos: max 1600 px, no metadata
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

Videos (15-second sweeps around a part) stay in `data/raw/` for now; frames are extracted later and prepared the same way.
