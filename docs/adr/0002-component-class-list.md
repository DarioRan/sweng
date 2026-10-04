# ADR 0002 — The frozen component class list

- **Status:** Proposed — becomes Accepted when the PR is approved by every decider
- **Date:** 2026-10-05
- **Deciders:** Sneha Chaudhary, Narmeen Sabah Siddiqui, Dario Ranieri, Yernur Polatbek
- **Issue:** #11 (T-306, Sprint 1, Vision, P1)
- **Blocks:** photo capture (T-309), dataset check, annotation (T-310)
- **Related:** ADR 0001 (public bicycle datasets), whose open item 2 this resolves

---

## Context

The detector must name the component in a user's photograph before the assistant answers from the manual (Rule 2: no component claimed without a detection). The class list is therefore the annotation schema for capture, annotation and training, and the vocabulary `/api/detect` returns in `Detection.label`. Changing it after annotation starts means relabelling, so it is frozen now.

A class is admitted only if it is:

1. **A drivetrain or brake component** — the scope the product is validated on.
2. **Visually distinct** in a close-up phone photograph, or, where it is not, flagged as a confusable pair so the error is measured rather than hidden.
3. **Covered by at least one Shimano dealer's manual**, so a detection always has a document to answer from.

## Decision

Eleven classes. The machine-readable schema is [`backend/app/vision/categories.json`](../../backend/app/vision/categories.json) (COCO `categories` block); this table is its human definition. Ids are fixed: annotations and trained weights refer to them.

| Id | Name | Definition — what gets a box | Shimano dealer's manuals | Example photo |
|---|---|---|---|---|
| 1 | `rear_derailleur` | The cage-and-pulley mechanism hung from the rear dropout that moves the chain across the cassette. Box includes the cage and both pulleys. | DM-RD0001 (MTB), DM-MARD001 | to capture (T-309) |
| 2 | `front_derailleur` | The cage on the seat tube, above the chainrings, that moves the chain between chainrings. | DM-FD0003, DM-FD0001 (MTB) | to capture (T-309) |
| 3 | `cassette` | The stack of sprockets on the rear hub. | DM-RACS001 (road), DM-MACS001 (MTB) | to capture (T-309) |
| 4 | `chain` | The roller chain. One box per visible run; a run broken by occlusion gets one box per segment. | DM-CN0001 | to capture (T-309) |
| 5 | `crankset` | Crank arms together with the chainrings and spider. Excludes the pedals. | DM-MBFC001, DM-MDFC001 | to capture (T-309) |
| 6 | `bottom_bracket` | The bearing cups visible at the frame's bottom-bracket shell, between the crank arms. | DM-MBFC001, DM-MDFC001 | to capture (T-309) |
| 7 | `pedal` | A pedal body, flat or clipless, on its crank arm. | DM-PD0002 (road), DM-MAPD001 (MTB) | to capture (T-309) |
| 8 | `shift_brake_lever` | A handlebar control that brakes, shifts, or both: a road dual control lever, an MTB brake lever, or a trigger shifter. | DM-RACBR01, DM-RADBR01, DM-MADBR01 | to capture (T-309) |
| 9 | `disc_brake_caliper` | The caliper on the fork or frame mount that grips the rotor. | DM-RADBR01 (road), DM-MADBR01 (MTB) | to capture (T-309) |
| 10 | `disc_rotor` | The metal disc bolted to the hub that the caliper grips. | DM-MADBR01, DM-RADBR01 | to capture (T-309) |
| 11 | `rim_brake_caliper` | A dual-pivot caliper rim brake at the fork crown or seatstay bridge. V-brakes and cantilevers are out of scope. | DM-RACBR01 | to capture (T-309) |

Supercategories: `drivetrain` (1–7), `control` (8), `brake` (9–11).

### Manual mapping: how it was checked

Every code above is the code on a dealer's manual published at si.shimano.com, matched to the class by the manual's title and the model numbers it covers (for example DM-RACBR01 covers the BR-R7000 caliper and the dual control levers used with it; DM-MADBR01 covers BL-M8100 and the RT-MT800 rotor). Checked 2026-10-05 from the si.shimano.com search listing; the site refuses scripted downloads, so the PDFs themselves were not opened. **Before Accepted, a decider opens one manual per class in a browser and ticks it off below.** No manual is indexed yet: this mapping is the list the corpus ingestion (T-203b) must index first, and "maps to an indexed manual" is met when it has.

### Example photos

One example photo per class comes from our own first capture session (T-309), stored with the captures, not in Git (§1.4, `data/` is ignored). Photos from the web are not used, as their licences are unrecorded. The column above is updated with the capture id of each example when the session is done.

## Confusable pairs

Flagged now so the confusion matrix reports them by name from the first trained detector.

| Pair | Why they are confused |
|---|---|
| `rear_derailleur` ↔ `front_derailleur` | Both are a metal cage around the chain; in a close-up there is little context for front or rear. |
| `cassette` ↔ `crankset` | Both are concentric toothed rings. |
| `disc_rotor` ↔ `crankset` | A drilled rotor and a chainring are both flat, perforated discs. |
| `disc_brake_caliper` ↔ `rim_brake_caliper` | Both are a compact brake body near the wheel. |
| `bottom_bracket` ↔ `crankset` | The bottom bracket is mostly hidden behind the crank arm; the boxes overlap heavily. |

## Overlap with DelftBikes

Resolves ADR 0001 open item 2. DelftBikes' 22 classes against our 11:

| Our class | DelftBikes class | Match |
|---|---|---|
| `chain` | chain | **Direct** |
| `pedal` | front pedal, back pedal | **Direct**, after merging the two |
| `shift_brake_lever` | front hand brake, back hand brake | **Possible** — depends on whether those boxes cover the lever or the brake on the wheel. Settled when the annotation format is inspected (ADR 0001 open item 4) |
| `rim_brake_caliper` | front hand brake, back hand brake | **Possible**, as above |
| `crankset` | — | None. DelftBikes' *gear case* is the enclosed chain guard of a Dutch city bike, not a sprocket; it hides the crankset and chain rather than labelling them |
| `rear_derailleur`, `front_derailleur`, `cassette`, `bottom_bracket`, `disc_brake_caliper`, `disc_rotor` | — | None |

Two of our eleven classes get labels straight from DelftBikes, two might, and seven get none. DelftBikes stays a source of pretrained features, as ADR 0001 decided. It is not a source of our labels. Whether to fine-tune the shared classes on its boxes is a question for T-201.

## Options considered

- **The ten candidate classes in #11, unchanged.** Rejected only to add `pedal`: it is covered by its own dealer's manuals, is a frequent repair question, and is one of the two classes that match DelftBikes directly.
- **Split `shift_brake_lever` into shifter and brake lever.** Rejected: on road bikes both are one part (a dual control lever), so the split would be undefined for half the bikes. Revisit if the detector confuses MTB brake levers with trigger shifters and the answers need to differ.
- **Include V-brakes and cantilevers in `rim_brake_caliper`.** Rejected: they look different from a dual-pivot caliper and are covered by other manuals. Adding them later is a new class, not a change to this one.
- **Chainring as its own class.** Rejected: on a photograph it is not separable from the crank arm it is bolted to, and the manuals document it with the crankset.

## Consequences

- **Frozen.** After Accepted, any change to an id, a name or a definition is an amendment to this ADR, with a relabelling plan for whatever was already annotated.
- `/api/detect` returns only these names in `Detection.label`. The contract shape (`label: str`) does not change. The list lives in `app.vision.LABELS` for the detector to use.
- The capture plan (T-309) covers every class, from several angles (ADR 0001 criterion 3), with extra images for each side of a confusable pair.
- The corpus ingestion (T-203b) indexes the manuals in the table above first.

## Open items before this ADR moves to Accepted

- [ ] Manual codes opened and confirmed in a browser, one per class
- [ ] Example photo recorded for each class after the first capture session
- [ ] PR approved by every decider

## References

- Issue #11 (T-306) — this decision
- ADR 0001 — public bicycle datasets, and the DelftBikes class list
- Shimano dealer's manuals: si.shimano.com, document codes as listed above
