# Shimano manual corpus (T-203)

The 25 Shimano dealer's manuals the assistant answers from. One row per manual in `provenance.csv`: source link, licence basis and retrieval date (Rule 4, US-24).

## How to get the PDFs

Each team member downloads the PDFs directly from Shimano, using the `source_url` column, into a local folder that is never committed or shared. The PDFs are not in this repository: `.gitignore` excludes `*.pdf`, and the plan forbids redistributing manufacturer manuals (§1.4).

## Licence basis

Shimano's terms of use (https://www.shimano.com/en/term_of_use.html, read 2026-10-06) allow viewing and downloading materials for private use only, require copyright notices to be kept, and prohibit redistribution, derivative works and use on other websites or networked environments. We therefore do not share the PDFs, even inside the team, and each member downloads their own copy.

si.shimano.com blocks automated access, so its own terms page could not be checked by script. If it states different terms, update this section.

Open question for the team: indexing these manuals and showing passages and figures in the assistant goes beyond private viewing. This is acceptable only as a private course prototype. Anything public would need Shimano's written permission.

## Coverage

Every class in `backend/app/vision/categories.json` (ADR 0002) is covered by at least one manual. The `components` column uses exactly those class names, separated by `|`, so retrieval can filter by the detected class.

## Notes

- Several codes in ADR 0002 are 11-speed manuals (DM-RACS001, DM-CN0001). Newer manuals were added for 12-speed parts: DM-RBCS001, DM-MACS010, DM-MACN001, DM-RARD010.
- DM-CN0001 is not included. Its English PDF was not found. DM-MACN001 and DM-CN0002 cover the chain class.
- Road rotors are coded SM-RT (for example SM-RT800 in DM-RADBR01), MTB rotors RT-MT (in DM-MADBR01).
- DM-TORQUE-04 is a torque chart across all series. It supports specification-first answers (US-14).
- Links without a revision number always serve the newest revision. The `revision` column records which one was downloaded.
- When Shimano publishes a new revision, download it, add a row, and retire the old one (US-26).
