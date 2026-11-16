# Shimano manual corpus (T-203)

The 27 Shimano dealer's manuals the assistant answers from. One row per manual in `provenance.csv`: source link, licence basis and retrieval date (Rule 4, US-24).

## How to get the PDFs

Each team member downloads the PDFs directly from Shimano, using the `source_url` column, into a local folder that is never committed or shared. The PDFs are not in this repository: `.gitignore` excludes `*.pdf`, and the plan forbids redistributing manufacturer manuals (§1.4).

Put them in `data/manuals/` at the root of the repository, keeping the file names from the `file_name` column. `data/` is git-ignored. The download has to be done by hand in a browser: si.shimano.com answers a script with HTTP 403 (checked 2026-10-12), and that block is not to be worked around.

## Indexing the manuals (T-203b)

```sh
docker compose --profile ingest run --rm ingest
```

This starts Qdrant, the object store and one ingestion run. For every manual in `provenance.csv` it:

1. **Parses** the PDF into text, page by page, in reading order (`pypdf`). The page number and the "To be continued on next page" line are dropped.
2. **Finds the section** of each page from the PDF's bookmarks, for example `MAINTENANCE > Replacing the bump stopper/holder (RD-M820)`.
3. **Chunks** the text. A page is one chunk whenever it fits the embedder, so the steps on a page stay together and every chunk cites exactly one page. A longer page is cut between steps. 96% of pages are a single chunk.
4. **Extracts the figures** of each page and uploads them to the `figures` bucket as `<manual>/p<page>-<n>.png`, and **renders every page** to `pages/<manual>/p<page>.png` (100 DPI). `/ask` shows the model the pages of the passages it answers from (ADR 0004).
5. **Embeds** each chunk with `EMBEDDER_MODEL` (`BAAI/bge-small-en-v1.5`, 384 dimensions) and also stores its keywords (BM25).
6. **Indexes** it in the Qdrant collection `manual_chunks`. Each chunk records its manual, page, section, figures, component classes, provenance, the manual's print date, and every part code its manual names (`parts`, such as `BR-R9270`). `/ask` uses `parts` to limit a question that names a part to the manuals that cover it: a page often gives a torque without repeating the models it applies to.

### Three things the real manuals decided

- **Chunks are sized in the embedder's tokens, not in characters.** The embedder reads 512 tokens and silently ignores the rest. A contents page is close to one token per character, so a 1,000-character chunk can be 945 tokens. The run reports the largest chunk of each manual and fails if one passes the limit.
- **A procedure is kept together page by page.** The manuals are laid out in pages: a continuation page repeats the section title. A chunk that ran over several pages could cite only one of them, and would not fit the embedder. So a long procedure is several chunks that share one `section` and follow each other by page.
- **Search uses meaning and keywords together.** Meaning alone cannot tell `CS-R9100` from `CS-R8000`: it ranked the right page 14th for a question naming the part, and missed another altogether. With keywords added, all five questions tried had their page in the best four.

### Figures

The manuals draw their figures as vector line art, and a few use pictures. There is no image file to pull out and **no caption**: a figure has part labels only. A figure is therefore found as a region dense with drawing strokes, or covered by a picture, and is cut from a render of the page. Its caption is the `section` of its page.

Known limits, seen in the crops: figures stacked closely in the newer step-table layout can come out as one crop, and text beside a figure can be cut at the edge.

### Making the figures searchable

A figure's part labels are in the page text, but what it shows (an exploded view, a tool on a bolt) is not written anywhere. A second step has the vision model (`LLM_LOCAL_MODEL`, ADR 0003) describe every figure in one or two sentences, and indexes the description beside the text as a point of kind `figure`:

```sh
docker compose --profile ingest --profile local run --rm ingest python -m app.corpus.captions
```

Run it after every ingestion: re-indexing a manual removes its figure points. The descriptions are cached per model in `/models/captions/`, so a rerun asks the model only about new figures. It took about 15 minutes for the 1,373 figures on an RTX 5070.

**A description is never evidence.** It was written by a model, not by Shimano. When a search finds one, `/ask` swaps it for the manual's own text of that page, and the description reaches neither the answering model nor the user. It decides only which page, and which figure, is found and shown.

### The report

One row per manual. The run exits with an error unless every manual is `ok` and every test question finds its page.

| Status | Meaning | What to do |
|---|---|---|
| `ok` | Every page was read, and the index and the bucket hold everything. | Nothing. |
| `MISSING` | The PDF is not in `data/manuals/`. | Download it. |
| `NO TEXT` | The PDF has pages but no text layer (a scan). | It needs OCR first. |
| `UNREADABLE` | The PDF could not be opened. | Download it again. |
| `INCOMPLETE` | The index or the bucket holds less than was produced. | Rerun. |
| `NO DATE` | The print date was not found on the last page. | Check the PDF's last page. |
| `TOO LONG` | A chunk is longer than the embedder reads. | A bug: report it. |

Below the table it lists the pages where no text could be extracted, and any PDF in the folder that is not in `provenance.csv`. Such a PDF is left out: nothing is indexed without a provenance row (Rule 4).

Rerunning is safe: a manual's old chunks and figures are removed before its new ones are written. Use `--recreate` after changing the embedder, and `--query` to see the best chunks for a question:

```sh
docker compose --profile ingest run --rm ingest python -m app.corpus.ingest --query "rear derailleur mounting torque"
```

### Test questions

`test_questions.csv` holds three questions with the manual and page that answer them, found by reading the manuals and not by searching. Every run searches for each one and passes it when its page is among the five chunks returned.

### State on 2026-11-16

| | |
|---|---|
| Manuals indexed | 27 of 27 |
| Pages | 945, each also stored as a page render |
| Chunks | 982 |
| Figures stored | 1,373, on 648 pages |
| Figures described and searchable | 1,373 of 1,373 |
| Pages with no text | none |
| Largest chunk | 510 tokens (limit 512) |
| Test questions | 3 of 3, each within the five chunks returned |

### When two manuals disagree

They do. The brake manual DM-RADBR01-11, printed 2025-04, gives a 2.5 mm hexagon wrench for the bleed screw of the ST-R7020 lever. The torque chart DM-TORQUE-04, printed 2023-12, lists that lever in its 2 mm row.

The rule (ADR 0004): the assistant gives both values, each with its manual and print date, the newer one first. It never picks one silently.

Ingestion does its part: it reads the print date from the last page of every manual (`© Apr. 2025 by SHIMANO INC.`) and stores it on each chunk as `published`. A manual without one is reported as `NO DATE`. `/ask` applies the rule in code (`backend/app/rag/pipeline.py`): it asks the model about one manual at a time, and when a value answer has a second manual naming the same part, asks about that one too and gives both values if they differ. The tested models did not apply it when only asked to (`bench/README.md`).

### Known weak point: tables

Text extraction flattens a table: a row's part, model, torque and tool end up on separate lines. On real torque tables several small models then gave the value of a neighbouring row (`bench/README.md`). `pypdf` has a layout mode that keeps a row on one line. It was looked at on one page and not adopted, because it changes the text of every page and all the checks above would have to be repeated.

What `/ask` does about it instead: the model also sees the rendered page, where the row is a row, and the grounding check refuses an answer whose value is not printed in the passage it cites (ADR 0004). A neighbouring row's value is printed there too, so the check alone does not catch it.

Also not done here: the PDFs are not copied to the object store and no row is written to PostgreSQL. That belongs to `POST /documents`.

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