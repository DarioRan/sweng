# ADR 0004 — How `/ask` answers: retrieval, the abstention gate, the safety gate and grounding

- **Status:** Proposed — becomes Accepted when the PR is approved by every decider
- **Date:** 2026-11-16
- **Deciders:** Sneha Chaudhary, Narmeen Sabah Siddiqui, Dario Ranieri, Yernur Polatbek
- **Issue:** T-307 (retrieval service), T-205 (grounded answering), T-501 (specification validator), T-502 (confidence and abstention threshold), T-503 (hazard list and safety gate), T-505 (attribution). Sprints 3 and 4, milestone M1
- **Related:** ADR 0003 (the language model); plan §1.3 (design rules) and §5.1 (request path); `docs/ask-pipeline.md` (a walk-through with examples); `bench/README.md` (how to rerun every number here)

---

## Context

`POST /api/ask` was a stub. This ADR records how it now answers, and the eight decisions in it that would be expensive to change. Each decision gives what was measured.

The plan fixes what `/ask` must guarantee (§1.3):

- **Rule 1.** Below a retrieval confidence threshold it abstains and makes no model call. Every number in an answer is checked against the retrieved text.
- **Rule 3.** Hazards are stated ahead of the step they concern. Professional-only work stops the procedure with a reason.
- **Rule 4.** Every passage is attributed to its manual. No numeric specification may come from a non-manufacturer source.

These are enforced by code outside the language model, so that the safety claim does not depend on the model behaving well.

All measurements are on the 27 manuals indexed on 2026-11-16, before DM-GN0001 (V-brakes, ADR 0002 Amendment 1) was added to the corpus, and on `bench/ask_questions.json`: 41 questions the manuals answer, with the pages that hold the answer found by reading the manuals, and 28 they do not answer (out of scope, other brands, parts that do not exist, facts a manual does not give). Every third question of each kind is held out as a test split: 13 answerable and 9 unanswerable. Choices are made on the other 47 and reported on both.

## The pipeline

```
question (+ component from the detector)
  3. retrieve   hybrid search, scoped to the manuals that name the part      retrieval.py
  4. gate       a manual names the part? best score >= 0.75? else abstain    gate.py
  5. safety     withhold professional-only passages                          hazards.py
  6. compose    the model reads one manual's passages and page images        generation.py
  7. validate   every step cited, every value printed on the cited page      grounding.py
  8. warnings   the manual's own warning sentences, ahead of their steps     hazards.py
```

The stage numbers are those of plan §5.1. `pipeline.py` holds the order. Stages 4, 5, 7 and 8 call no model.

## Decisions

### 1. Text retrieval, with the page shown to the model as an image. Not VisRAG

**Decision.** Passages are found by searching text. The language model then reads the retrieved passages *and* the rendered pages they come from (two page images by default).

**Why not retrieve by page image (VisRAG, ColPali-class models).**

- The manuals are born digital. All 945 pages have a text layer; none needs OCR.
- A repair question names its part by a code. `CS-R9100` and `CS-R8000` must be told apart exactly, which is what keyword search does and what an image retriever does poorly. Search by meaning alone already ranked the right page 14th for such a question (`docs/corpus/README.md`).
- An image retriever is several gigabytes more, on machines where the team has little disk, and it stores many vectors per page.

**Why still show the page.** Text extraction flattens a table: a row's part, torque and tool end up on separate lines, and models then give a neighbouring row's value (ADR 0003). On the page image the row is a row.

**Measured.** `qwen3.5:4b` through the whole pipeline, same questions and threshold:

| | Right (of 41) | Wrong | Lost | Seconds per answer (median) |
|---|---|---|---|---|
| Passages and two page images | 36 | 1 | 4 | 1.4 |
| Passages only | 34 | 2 | 5 | 0.9 |

Two more right and one fewer wrong, for half a second. That is weak evidence: an earlier text-only run of the same model gave 33 right and 3 wrong, so one question either way is what a rerun changes. Both text runs were behind the run with images, and the reason to expect a gain is sound, so images are on by default. For two other models, images made the answers worse (ADR 0003). `ASK_PAGE_IMAGES` is a setting, and 0 turns it off.

**Figures are searchable too.** The figures have no caption. The language model writes one or two sentences about each of the 1,373 figures once, at indexing time, and the sentence is indexed (`app/corpus/captions.py`). A description is written by a model, not by Shimano, so it is never evidence: a search that finds one is sent on to the manual's own text of that page.

### 2. The part named in the question scopes the search

**Decision.** If the question contains part codes (`BR-R9270`, `TL-SR24`), only the manuals that name every one of them are searched. Each chunk carries the list of part codes its manual names (`parts`), built at indexing time. `BR-R9100/R8000/R7000` counts as three parts.

**Why.** A page often prints "B-axle 10 - 12 N·m" without repeating the models it applies to, so the page text alone cannot be matched against the part. And without a scope, a question about `RD-R8150` was answered from the manual of a different rear derailleur family whose pages look the same.

**Measured.** The answer page was among the five passages for 37 of 41 questions, against 35 for the first design, which did not scope by part. By the wider rule used from here on, where a torque-chart page that names the part and prints the expected value also counts, it is 39 of 41.

It also gives the cheapest abstention there is. A question about a part no manual names (`BR-Z9999`) finds nothing and stops, with no scoring and no model.

### 3. The detected component is a hint, not a wall

**Decision.** `confirmed_component` narrows the search only when that does not cost a clearly better passage:

1. Search every manual, and search the component's manuals.
2. If the best passage of every manual scores more than 0.02 higher than the best passage of the component's manuals, the question is about something else: use every manual.
3. Otherwise use the component's manuals, with the component's name added to the question.
4. If the component's manuals then give no answer, search every manual once more.

**Why.** The photograph says what the user is looking at, not what the problem is. A photograph of the pedals with "the bike barely stops" is a question for the brake manuals. The plan's request path filters retrieval to the confirmed component (§5.1, stage 3); as a hard filter, that would make this question unanswerable. But the component is what makes a vague question answerable at all (US-02, US-13).

**Measured.** On the 32 labelled questions whose manual does not cover every class, counting those where the gate opens with the answer page among the passages:

| Component given | How it is used | Kept |
|---|---|---|
| None | - | 29 of 32 |
| The right class | Hard filter | 29 |
| The right class | As decided | 30 |
| A wrong class | Hard filter | **6** |
| A wrong class | As decided, before step 4 | **26** |

And on 13 questions written for this (`bench/scope_questions.json`): of 8 vague questions with the right photograph ("How tight should this be?" with a pedal), 7 were searched in the component's manuals and all five passages then came from them. 6 of those 7 passed the gate; without the component, 4 of the 6 would have been refused. Of 5 questions about another part than the one photographed, 4 were searched in every manual.

**Limit.** The margin of 0.02 was set by eye on these 45 questions. It must be recalibrated on real detections once the detector exists (T-407).

### 4. Confidence is the embedder's own similarity. No reranker

**Decision.** The confidence of a passage is the cosine similarity between the question and the passage, from the embedder that indexed it (`bge-small-en-v1.5`). The vectors are already in the index, so scoring costs nothing. The five passages are kept in the order the hybrid search gave them.

**Why this needed deciding.** The hybrid search merges its two rankings by rank. Its score says which passage is better, never whether any is good enough; a threshold on it is meaningless. The placeholder threshold of 0.5 would have refused every question. Something has to score passages on an absolute scale, and the usual answer is a cross-encoder reranker.

**Measured.** Five cross-encoders against the embedder's similarity, each with the threshold its own calibration chose. *Separation* is how well the best score alone tells an answerable question from an unanswerable one (1.0 perfect, 0.5 chance).

| Scorer | Size | Calibrate: kept | refused | separation | Test: kept | refused | separation |
|---|---|---|---|---|---|---|---|
| **Embedder similarity (`dense`)** | 0 | 26/27 | 19/19 | 1.00 | 12/12 | 8/9 | 0.98 |
| `ms-marco-MiniLM-L-6-v2` | 80 MB | 26/27 | 18/19 | 0.98 | 11/12 | 8/9 | 0.99 |
| `ms-marco-MiniLM-L-12-v2` | 120 MB | 26/27 | 18/19 | 1.00 | 11/12 | 8/9 | 0.99 |
| `jina-reranker-v1-tiny-en` | 130 MB | 27/27 | 15/19 | 0.99 | 11/12 | 7/9 | 0.98 |
| `jina-reranker-v1-turbo-en` | 150 MB | 26/27 | 16/19 | 0.98 | 11/12 | 8/9 | 0.96 |
| `bge-reranker-base` | 1 GB | 26/27 | 17/19 | 0.97 | 10/12 | 8/9 | 0.97 |

No reranker did better than the similarity the index already has. Two more things were measured and rejected:

- **Letting the scorer reorder the passages.** For every scorer, its own order reached the same number of answer pages as the search's order or fewer (24 against 27 of 28 for the embedder). In the first design a cross-encoder moved the right page from rank 1 out of the top five for two questions.
- **Adding the neighbouring pages of the best passage.** With the search's order, no more answer pages were reached, for any scorer.

Both remain as options in `retrieval.py`, off. `RETRIEVAL_SCORER` can name a cross-encoder if a larger question set later shows one is worth it.

### 5. The abstention threshold is 0.75, and the gate runs before any model call

**Decision.** `/ask` abstains, without calling the model, when no manual names the part in the question, or when the best passage scores under `RETRIEVAL_CONFIDENCE_THRESHOLD = 0.75`. When the gate opens, all five passages go on: the threshold decides whether to answer, not what to read.

**The rule that chose 0.75**, fixed before looking at the numbers: the highest threshold that still keeps at least 95% of the answerable questions the search reaches, on the calibrate split. A lost answer has no second chance. A question let through by mistake still meets two more defences: the model, which may abstain, and the check of decision 8.

**Measured.**

| | Calibrate | Test (held out) |
|---|---|---|
| Answer page among the five passages | 27 of 28 | 12 of 13 |
| Of those, the gate lets through | 26 of 27 | 12 of 12 |
| Unanswerable questions refused, no model call | 19 of 19 | 8 of 9 |

Five of the 28 refusals come from the part check alone, at no cost.

**How far to trust it.** The margin is thin. The best score of an answerable question ranged from 0.74 to 0.88; of an unanswerable one that found any passage, from 0.54 to 0.76. They overlap around the threshold: one answerable question scores 0.74 and is refused, one unanswerable one scores 0.76 and gets through (a SRAM derailleur), and six answerable questions pass by 0.02 or less. So the gate is a strong first filter and not a guarantee. The threshold must be recalibrated whenever the embedder or the corpus changes: `python -m app.rag.calibrate`.

### 6. Hazards come from a list, in the manual's words. The model is not asked

**Decision.** The hazard list is `backend/app/rag/hazards.json`: patterns matched against the sentences of the manual passages. It is used twice, both times by code:

- **Before the model.** A passage that matches a `stop` mark is withheld from the model, so the model cannot describe that work. The answer is `truncated`, with the manual's sentence as `stop_reason` (FR-09).
- **After the check.** Every sentence of a cited page that matches the list is attached to the answer, ahead of the first step taken from that page (US-06). The text of a hazard is always the manual's sentence, never ours and never the model's.

The model's output has no hazard field. A model cannot leave out a warning it is not responsible for.

**The starter list.** Twelve patterns written from the wording the 27 manuals actually use ("serious injury", "become hot", "wear gloves", "may break"). On the corpus they match 316 sentences in 115 of the 982 chunks. Sentences that the manual addresses to a dealer in some situation ("If the chain keeps skipping during use, consult the place of purchase") are attached as hazards marked `professional_only`. The preface every manual repeats is ignored.

**What is not decided: the `stop` marks.** The list has none. Shimano's dealer's manuals do not mark single procedures as professional-only; each says once, in its preface, that the whole manual is meant for professional mechanics. Taken literally that would stop every answer. Which procedures the assistant must refuse to walk a home user through (bleeding a hydraulic brake? cutting a brake hose?) is a judgement about users and risk, and belongs to the team (T-503) and later to the administrator (US-27). The mechanism is built and tested; adding a mark is one line of JSON.

The model can also stop on its own: if a passage says a job is for a dealer, it answers `professional_only` (prompt rule 5), and the check accepts that only if a passage does say so.

### 7. One manual per model call. Two manuals that disagree are both reported

**Decision.** The passages are grouped by manual. The model is asked about one manual at a time, best first, up to three. If the first has no answer, the next is asked. When the question names a part and the answer is a single value, the next manual that names the part is asked too; if its value differs, both are returned, the newer manual first, each with its manual and print date.

**Why.** Shimano's manuals do disagree: the brake manual (printed 2025-04) gives a 2.5 mm wrench for the bleed screw of the ST-R7020 lever, the torque chart (2023-12) lists that lever in its 2 mm row. Asked in the prompt to give both, every model tested gave one and said nothing of the other (ADR 0003). A model that sees one manual at a time cannot choose between two.

**Measured.** The ST-R7020 question returns both values in the right order, with either page-image setting. It costs model calls: 59 for the 41 questions that reached the model. 14 of them took a second or third call, to try the next manual or to compare two.

**Limit.** Two manuals are compared only when the question names a part code. Without one there is no way to know that two lock rings are the same lock ring.

### 8. The answer is checked against the cited page. One failure abstains the whole answer

**Decision.** After the model answers, code checks that:

- every step cites a passage it was given;
- every value in a step is printed on a page that step cites. One end of a printed range is not a value: "3 N·m" is refused when the page says "2.5 - 3 N·m";
- every part code in the answer is named by a passage or its manual;
- every value is printed in a manufacturer's manual (Rule 4);
- a `professional_only` answer has a passage that says so.

If any check fails, the answer from that manual is refused, and the response is an abstention with the reason unless another manual answers.

**Deviation from the plan.** The plan (§5.1, stage 7) strips unmatched values and marks the answer incomplete. This refuses the whole answer. A torque answer with its torque stripped is no answer, and a procedure with a step removed is worse than no procedure. The contract also has no "incomplete" status.

**What it cannot catch.** A value that is printed on the cited page but belongs to another row or another bolt. The one wrong answer in the test is of this kind (`docs/ask-pipeline.md`, example 9).

## The whole pipeline, measured

`qwen3.5:4b`, two page images, threshold 0.75, 2026-11-16, RTX 5070 (`bench/results/`):

| | All 69 questions | The 22 held out |
|---|---|---|
| Answerable, answered correctly | 36 of 41 | 11 of 13 |
| Answered wrongly | 1 | 1 |
| Answerable, abstained on | 4 | 1 |
| Unanswerable, refused | 28 of 28 | 9 of 9 |
| Refused before any model call | 27 | 8 |

With a component class that the answer's manuals do not cover passed on 32 of the answerable questions, as a wrong detection would, the result is the same: 36 right, 1 wrong, 4 lost, 28 refused, for 66 model calls in place of 59 (`bench/results/20261116-203446-ask.md`).

Six other models were run through the same pipeline. The nearest gave 9 wrong answers (ADR 0003).

Against milestone M1, "a question against the indexed corpus returns a cited, attributed answer, or a correct abstention, with hazards ordered ahead of their steps": met on these questions, with one wrong answer in 41.

## Consequences

- **New settings:** `RETRIEVAL_SCORER` (default `dense`), `RETRIEVAL_CONFIDENCE_THRESHOLD` (0.75), `ASK_PAGE_IMAGES` (2). `LLM_BACKEND` now defaults to `local`: there is no hosted model (ADR 0003), and `/ask` returns 503 for `hosted`.
- **`/ask` needs Ollama, which is not in the default stack.** `docker compose up` alone gives an `/ask` that abstains correctly and answers 503, with the command to run, for anything that needs the model. Whether Ollama should start by default is open (below).
- **Ingestion does more.** It renders every page (about 150 MB for 945 pages) and records `parts`. Describing the figures is a second, optional step of about 15 minutes on a GPU, to be rerun after every ingestion.
- **The contract is unchanged in shape.** `AskResponse.stop_reason` now also carries the reason for an abstention. One endpoint was added, `GET /api/figures/{key}`, which serves the image a citation's `figure` names, or a page render.
- **Latency.** An abstention at the gate takes about 50 ms. An answer takes one model call, sometimes two or three: 1.4 seconds median on an RTX 5070, 2.1 seconds for nine in ten. On a CPU a model call is about ten seconds (ADR 0003).
- **The index layout changed.** Rerun the ingestion after pulling this.

## Limits and open items

1. **The numbers flatter the pipeline.** It was fixed after reading its failures on these same 69 questions, test split included. Only the threshold was chosen without the test split. The clean measurement is the gold set and the adversarial set (T-603, T-604), written by someone who has not tuned this code.
2. **69 questions is small**, and most answerable ones ask for one value. Procedures, symptoms and tables with many rows are under-represented.
3. **The `stop` marks are not authored** (decision 6). Until they are, FR-09 is exercised only by the model's own `professional_only` answers and by tests.
4. **Right page, wrong row.** No check catches it (decision 8). Most likely when the question names no part code. Worth trying: require the cited sentence to share the question's key noun, or ask the user to confirm the part when no code is given.
5. **Symptom questions** ("the bike barely stops") score low and are mostly refused. US-16 needs an index of symptoms, not only of procedures.
6. **Procedures over several pages** may come back with only the retrieved pages' steps.
7. **Should Ollama start with the default stack?** `/ask` needs it; it adds a 3 GB image and a 3.3 GB model to every clean checkout (NFR-04). Left to the team.
8. **The margin of decision 3** waits for the detector.
9. **Not part of this ADR:** saving answers to the session (T-407), authentication on the endpoint (T-402), the frontend.
10. **V-brakes are not measured.** DM-GN0001 and class 12 arrived after these runs. Index it, add V-brake questions to `bench/ask_questions.json`, and rerun both tests; the threshold may move.
11. **Before Accepted**, a decider reruns `app.rag.calibrate` and `app.rag.evaluate` (`bench/README.md`) and checks the tables above.
