# Shimano manual corpus (T-203)

The 27 Shimano dealer's manuals the assistant answers from. One row per manual in `provenance.csv`: source link, licence basis and retrieval date (Rule 4, US-24).

## How to get the PDFs

Each team member downloads the PDFs directly from Shimano, using the `source_url` column, into a local folder that is never committed or shared. The PDFs are not in this repository: `.gitignore` excludes `*.pdf`, and the plan forbids redistributing manufacturer manuals (§1.4).

## Licence basis

The `licence_basis` column holds a short code, defined here once instead of on every row.

| Code | Meaning |
|---|---|
| `shimano-tou-private` | Downloaded from si.shimano.com. Copyright SHIMANO INC. Private use only under Shimano's terms of use (below). Kept locally by each team member for a private course prototype. Not redistributed. |

A manual from another source with different terms gets a new code in this table.

Shimano's terms of use (https://www.shimano.com/en/term_of_use.html, read 2026-10-06) allow viewing and downloading materials for private use only, require copyright notices to be kept, and prohibit redistribution, derivative works and use on other websites or networked environments. We therefore do not share the PDFs, even inside the team, and each member downloads their own copy.

si.shimano.com blocks automated access, so its own terms page could not be checked by script. If it states different terms, update this section.

Open question for the team: indexing these manuals and showing passages and figures in the assistant goes beyond private viewing. This is acceptable only as a private course prototype. Anything public would need Shimano's written permission.

## Coverage

Every class in `backend/app/vision/categories.json` (ADR 0002) is covered by at least one manual. The `components` column uses exactly those class names, separated by `|`, so retrieval can filter by the detected class.

## Notes

- Every code in ADR 0002 is included. Two of them are 11-speed manuals (DM-RACS001 for road cassettes, DM-CN0001 for chains), kept because many bikes still run 11-speed. DM-MACS001 covers the 12-speed MTB cassettes CS-M9100, CS-M8100, CS-M7100 and CS-M6100. Further manuals were added for newer 12-speed parts (DM-MACS010, DM-MACN001, DM-RARD010) and for 7 to 9-speed cassettes on entry-level bikes (DM-RBCS001).
- The chain class is covered by DM-CN0001 (11-speed), DM-MACN001 (12-speed) and DM-CN0002 (CN-LG500 LINKGLIDE and SM-CN900-11).
- Road rotors are coded SM-RT (for example SM-RT800 in DM-RADBR01), MTB rotors RT-MT (in DM-MADBR01).
- DM-TORQUE-04 is a torque chart across all series. It supports specification-first answers (US-14).
- Every `source_url` names the exact revision (`DM-<code>-<revision>-ENG.pdf`), so the link and the `revision` column always point to the same file.
- When Shimano publishes a new revision, download it, add a row, and retire the old one (US-26).