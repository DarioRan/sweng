# Hazard list (Rule 3, T-503)

`hazards.json` lists the hazards the assistant must state **before** the step they concern, and the work it must **not describe at all**. `hazards.py` applies the list to the retrieved procedure as plain code, before the model is called. Only the steps it keeps reach the model.

## How a hazard is matched

A hazard applies to a step when the step's component is in `components` (`"*"` means any component) **and** one of the regular expressions in `patterns` matches the step text (case-insensitive).

- **Warning** (`professional_only: false`): stated once, with `before_step` set to the first step it applies to.
- **Professional-only** (`professional_only: true`): the procedure stops at the first step it matches. That step and every later one are removed, the status is `truncated`, and `stop_reason` gives the `reason` and the manual page without describing the step.

The `text` is our own wording, never a quote. The Shimano manuals may not be redistributed (§1.4), and this repository is public. Each entry cites `document_id`, `revision` and the printed `pages` it was written from, and the answer shows that citation (Rule 4).

## What counts as professional-only

The dealer's manuals are written for trained mechanics as a whole (page 3 of each), so they mark no single step as professional-only. A step is marked professional-only when at least one of these holds:

1. **The manual sends the rider to a dealer.** It says to consult a dealer or the place of purchase (QUICK-LINK removal, protruding pistons, a damaged carbon lever).
2. **The manual forbids it.** It says not to remove or disassemble the part (caliper pistons, the shifting lever unit), or the job takes apart a mechanism the rider's documents never cover (the rear derailleur's spring-loaded clutch).
3. **It opens the hydraulic brake system**, the job cycling repair guides consistently leave to a shop. This covers bleeding and changing the mineral oil, and cutting or replacing a hose, which needs a bleed afterwards (DM-GN0001 p. 78).

Jobs those same guides treat as normal home maintenance are **warnings, not stops**. These include brake pads (including pushing the pistons back), cables, chain, cassette and derailleur adjustment. Bottom bracket and headset bearing service will also be professional-only under rule 3's reasoning once their manuals are in the list.

## Adding a hazard

1. Read the hazard in the manual PDF you downloaded (see `docs/corpus/README.md`). Note the revision and printed page.
2. Add an entry in your own words. Keep `patterns` narrow, so that a normal step such as "Remove the bleed spacer" does not trigger the bleeding stop.
3. Add or extend a procedure in `tests/test_hazards.py`, and run `pytest tests/test_hazards.py`.

## Manuals read so far

DM-CN0001 (07), DM-FD0001 (03), DM-GN0001 (29), DM-LACS001 (01), DM-LADBR01 (01), DM-MARD001 (06), DM-RACBR01 (03), DM-SL0002 (07).

DM-GN0001 and DM-LADBR01 were read at an older revision than the one in `provenance.csv` (30 and 04). Check their page numbers when you download the listed revision.
