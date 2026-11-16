# Measuring `/ask`

Three tests, from the narrowest to the widest. Each answers a different question, and each decision in the ADRs rests on one of them.

| Test | Question it answers | Calls a language model? | Decision |
|---|---|---|---|
| 1. [Models on fixed passages](#test-1-models-on-fixed-passages) | Given the same passages, which model answers, cites and abstains best? | Yes | ADR 0003, first pass |
| 2. [Search and gate](#the-search-and-the-gate) | Which passages should `/ask` read, and below what score should it abstain? | No | ADR 0004, decisions 2 to 5 |
| 3. [The whole pipeline](#every-model-through-the-pipeline) | What does the user get, and with which model? | Yes | ADR 0003 and ADR 0004 |

All three score by fixed rules. There is no LLM judge anywhere.

## The questions

| File | What it holds | Used by |
|---|---|---|
| `cases.json` | 22 invented cases: passages written for the test, with invented part codes and values | Test 1 |
| `corpus_questions.json` | 16 questions on the real manuals, with the pages that answer them | Test 1 |
| `ask_questions.json` | 69 questions on the real manuals: 41 answerable, with their pages, and 28 that the manuals do not answer. Includes the 16 above | Tests 2 and 3 |
| `scope_questions.json` | 13 questions with a component, as the detector would give: 8 vague ones, and 5 where the photograph shows another part than the problem | Test 2 |

No file holds manual text. A question records the manual and page that answer it, found by reading the manuals, and the value a right answer contains.

**The split.** In `ask_questions.json`, every third question of each kind is marked `"split": "test"`: 13 answerable and 9 unanswerable. The threshold is chosen on the other 47 and reported on both.

**What counts as the answer page.** The pages a question lists. The torque chart repeats many values of the other manuals, so a page that is not listed also counts when it names the question's part and prints every expected value (`backend/app/rag/labels.py`).

**The 28 unanswerable questions** are of four kinds: outside the manuals altogether (tyre pressure, saddle height), other brands (SRAM, Campagnolo, Magura), real Shimano parts asked for something a manual does not give (weight, price, service life), and parts that do not exist (`RD-M9999`), where the search returns the pages of their real neighbours.

## Results, 2026-11-16

Ollama 0.40.3, RTX 5070. Reports: `results/20261116-202934-calibration.md` (test 2), `results/20261116-203244-ask.md` (test 3), `results/20261116-203446-ask.md` (test 3 with a wrong component).

### The pipeline with the chosen model

`qwen3.5:4b`, two page images, threshold 0.75:

| | All 69 | The 22 held out |
|---|---|---|
| Answerable, answered correctly | **36 of 41** | 11 of 13 |
| Answered wrongly | **1** | 1 |
| Answerable, abstained on | 4 | 1 |
| Unanswerable, refused | **28 of 28** | 9 of 9 |
| Refused before any model call | 27 | 8 |
| Seconds per answer, median / nine in ten | 1.4 / 2.1 | |

### Every model through the pipeline

| Model | Page images | Right (of 41) | Wrong | Lost | Refused (of 28) | Stopped by the check | Seconds per answer |
|---|---|---|---|---|---|---|---|
| **`qwen3.5:4b`** | **2** | **36** | **1** | 4 | **28** | 0 | 1.4 |
| `qwen3.5:4b` | 0 | 34 | 2 | 5 | 28 | 0 | 0.9 |
| `qwen3.5:9b` | 0 | 36 | 2 | 3 | 28 | 0 | 1.4 |
| `qwen3.5:9b` | 2 | 34 | 5 | 2 | 28 | 0 | 2.5 |
| `gemma4:e2b` | 0 | 32 | 9 | 1 | 27 | 0 | 0.6 |
| `granite4.2:3b` | 0 | 28 | 11 | 3 | 27 | 2 | 0.7 |
| `gemma4:e2b` | 2 | 27 | 12 | 3 | 27 | 4 | 0.8 |
| `phi4-mini` | 0 | 25 | 11 | 5 | 28 | 2 | 0.7 |
| `llama3.2:3b` | 0 | 25 | 11 | 5 | 28 | 12 | 0.7 |
| `gemma3:4b` | 2 | 23 | 13 | 6 | 27 | 5 | 1.7 |
| `gemma3:4b` | 0 | 20 | 19 | 3 | 27 | 3 | 0.9 |
| `qwen2.5:3b` | 0 | 18 | 3 | 20 | 28 | 22 | 1.4 |

*Stopped by the check*: questions where the grounding check refused an answer the model gave. `granite4.2:3b`, `phi4-mini`, `llama3.2:3b` and `qwen2.5:3b` cannot read images.

- **`qwen3.5:4b` gives 1 wrong answer; the other labs' models give 9 to 19.** `qwen2.5:3b` gives 3 by abstaining on half the answerable questions.
- **The gate is the same for every model**, so 27 of the 28 refusals are identical. The 28th question, a SRAM derailleur torque, reaches the model: three models invent an answer from a Shimano page.
- **The check catches a lot for the weaker models** (12 answers for `llama3.2:3b`, 22 for `qwen2.5:3b`, 19 of those for a reply that was not valid JSON) and still leaves them 11 and 3 wrong answers. What remains wrong has passed the check: a value that is printed on the cited page but belongs to another part or bolt, or an answer with no value in it.
- **`qwen3.5:9b` is no better** at twice the size.
- **Page images**: slightly better for `qwen3.5:4b`, worse for `gemma4:e2b` and `qwen3.5:9b`. One or two questions is what a rerun changes.

### The search and the gate

| | Calibrate (47) | Test (22) |
|---|---|---|
| Answer page among the five passages | 27 of 28 | 12 of 13 |
| Of those, the gate lets through | 26 of 27 | 12 of 12 |
| Unanswerable questions refused, no model call | 19 of 19 | 8 of 9 |

Chosen: the embedder's own similarity as the score, the search's order, no neighbouring pages, threshold 0.75. Five cross-encoder rerankers were measured against it and none did better; the table is in ADR 0004 and in the report.

### The detected component

| Component given | How it is used | Answer page kept, at the gate (of 32) | Right answers, whole pipeline (of 41) |
|---|---|---|---|
| None | - | 29 | 36 |
| The right class | Hard filter | 29 | |
| The right class | Hint (what `/ask` does) | 30 | |
| A wrong class | Hard filter | 6 | |
| A wrong class | Hint (what `/ask` does) | 26 | 36 |

### How far to trust these numbers

- **They flatter the pipeline.** It was fixed after reading its failures on these same questions, test split included. Only the threshold was chosen without the test split.
- **The questions were written by the person who built the pipeline.** The gold set of 30 and the adversarial set of 20 (T-603, T-604) are the independent measurement.
- **69 questions separate one mistake from ten, not one from two.** A rerun of the same model moved a result by one question.
- **Most answerable questions ask for one value.** Procedures, symptoms and long tables are under-represented.
- **Times depend on the machine.** Compare them within one run only.

## Run them

The manuals must be indexed first (`docs/corpus/README.md`), and for tests 1 and 3 Ollama must be able to pull the models (about 3 GB each).

```sh
# Test 1: models on fixed passages. Starts Ollama and the runner only.
docker compose --profile bench run --rm llm-bench

# Test 2: search and gate. No model. About 1 minute for the default scorer.
docker compose --profile ingest run --rm -v "$PWD/bench:/bench" ingest \
    python -m app.rag.calibrate /bench/ask_questions.json \
    --scope /bench/scope_questions.json --out /bench/results

# Test 3: the whole pipeline, with the configured model. About 3 minutes on a GPU.
docker compose --profile ingest --profile local run --rm -v "$PWD/bench:/bench" ingest \
    python -m app.rag.evaluate /bench/ask_questions.json --out /bench/results
```

Each writes `results/<date-time>-….md`: the tables, then every question that went wrong and why. That file is the record to commit. Raw answers quote the manuals, so they go to `bench/data/`, which is git-ignored.

Useful options:

```sh
# Test 2: compare scorers ('dense' is the embedder's own similarity, the others are cross-encoders)
... python -m app.rag.calibrate /bench/ask_questions.json \
    --scorers dense,Xenova/ms-marco-MiniLM-L-6-v2,BAAI/bge-reranker-base

# Test 3: several models, with and without page images; delete each model after its run
... python -m app.rag.evaluate /bench/ask_questions.json \
    --models qwen3.5:4b,gemma4:e2b --images 2,0 --remove-after --out /bench/results

# Test 3: give every answerable question a component class its manuals do not cover
... python -m app.rag.evaluate /bench/ask_questions.json --wrong-component

# With an NVIDIA GPU, start Ollama with it first (see the notes in docker-compose.gpu.yml)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile local up -d ollama
```

After changing the embedder, the corpus or the scorer, rerun test 2 and set `RETRIEVAL_CONFIDENCE_THRESHOLD` to the threshold it chooses. After changing the model or the prompt, rerun test 3.

## Reading a report

**Test 2** (`…-calibration.md`), for each scorer:

- *reached*: answerable questions whose answer page is among the passages selected. Only these can be answered at all.
- *kept*: of those, the ones the gate lets through.
- *refused*: unanswerable questions the gate closes on.
- *separation*: how well the best score alone tells a reached question from an unanswerable one, whatever the threshold (1.0 perfect, 0.5 chance).
- The threshold is the highest that keeps at least 95% of the reached questions of the calibrate split. The rule is in `backend/app/rag/calibrate.py` and was fixed before the numbers were read.

**Test 3** (`…-ask.md`), for each model:

- *right*: the expected value, citing a page that holds it.
- *wrong*: a wrong value, a page that does not hold the answer, or any answer to an unanswerable question. **This is the number to watch.**
- *lost*: an answerable question abstained on. The report says where: at the gate, by the model, or by the check.
- *refused*: unanswerable questions abstained on.

## Adding a question

Add an entry to `ask_questions.json`:

```json
{"id": "a30", "category": "fact", "split": "calibrate",
 "question": "What is the tightening torque for …?",
 "sources": [[["DM-MARD001-06", 9]]],
 "must_include": ["10-12"], "must_exclude": ["8-10"]}
```

- `sources`: the manual and page that hold the answer, found by **reading the manual, not by searching**. One group for a fact; two groups for two manuals that disagree, the newer manual's value first in `must_include`, with `"ordered": true`.
- `must_include`: what a right answer contains. A nested list means any one of its items.
- `must_exclude`: values that belong to another part or row.
- A question the manuals do not answer has no `sources`; say why in `why`.
- Give every third new question `"split": "test"`.

## Test 1: models on fixed passages

Which local model should answer `/ask`? This test puts the same questions, with the same passages, to several Ollama models and scores how well each one stays on the passages, cites its sources and abstains. It was the basis of ADR 0003 before the pipeline existed, and it is still the quickest way to try a new model.

Run of 2026-10-12, Ollama 0.40.3, on an RTX 4000 Ada:

| Model | Invented (22) | Real (16) | Both (38) | Invented an answer when there was none (of 9) | Wrong value on real passages (of 11) |
|---|---|---|---|---|---|
| `granite4.2:3b` | 17 | 14 | 31 | 2 | 0 |
| `qwen3.5:4b` | 18 | 12 | **30** | **0** | 1 |
| `gemma4:e2b` | 15 | 12 | 27 | 3 | 1 |
| `phi4-mini` | 15 | 10 | 25 | 3 | 1 |
| `llama3.2:3b` | 12 | 9 | 21 | 4 | 2 |
| `qwen2.5:3b` | 14 | 6 | 20 | 2 | 3 |
| `gemma3:4b` | 13 | 4 | 17 | 4 | 2 |

Full tables: `results/20261012-215558.md` (invented) and `results/20261012-215750-corpus.md` (real passages). Without a GPU (`results/20261012-220833-cpu.md`, 24 CPU cores): `qwen3.5:4b` 10.7 seconds an answer, `granite4.2:3b` 5.7, `llama3.2:3b` 4.1.

**Why test 3 was needed.** This test put `granite4.2:3b` one case ahead of `qwen3.5:4b`. Through the pipeline `granite4.2:3b` gives 11 wrong answers and `qwen3.5:4b` gives 1. The passages here were chosen by hand to hold the answer in 29 of the 38 cases; a real search often returns a page that is close but is not the page, and that is where the two models differ. The one column of this test that predicted it is "invented an answer when there was none".

Two things this test asks of the model are now done by code, so its scores on them no longer matter: reporting hazards (the hazard list does it) and giving both values when two manuals disagree (the pipeline asks one manual at a time). See ADR 0004.

### What is tested

The model's job as the first design of `/ask` had it. It receives the manual passages a search returned (three in the invented cases, five in the real ones) and a question, and must reply with JSON, a cut-down `AskResponse`:

```json
{ "status": "answered", "answer": "9-11 N·m", "citations": ["P2"], "hazards": [] }
```

Every model gets the same prompt and settings: temperature 0, a fixed seed, and thinking turned off. Thinking is off because a reasoning model otherwise spends its whole output budget on it: `qwen3.5:4b` took 20 seconds and returned an empty answer with thinking on, and answered correctly in under a second with it off.

The invented cases:

| Category | Cases | What it checks |
|---|---|---|
| `fact` | 8 | Find one value (torque, wear limit, tool). The other passages hold the same kind of value for a different part, so the model has to read the part code. |
| `unanswerable` | 5 | The passages look relevant but do not contain the answer. The model must abstain, not guess. |
| `hazard` | 4 | The passages carry a warning. The answer must pass it on, including one job that only a dealer may do (Rule 3). |
| `multi` | 3 | The answer needs two values from two passages, both cited. |
| `conflict` | 2 | Two manuals give different values for the same part. The answer must give both, the newer manual's first, and cite both. |

**Every passage in `cases.json` is invented.** The part codes, manual codes and values are not Shimano data and must never be used for a repair. A model cannot know an invented value, so a correct answer proves it read the passage and did not answer from memory.

There is no LLM judge. Each case lists what the answer must contain, and `run.py` checks it with plain rules. A case is passed only when all of these hold:

- **Status**: `answered` or `abstained`, as the case expects.
- **Facts**: every expected value is in the answer, and no value from the wrong part is.
- **Citations**: exactly the passages that hold the answer. A missing or an extra citation fails. In a real case a fact can be on several pages, and citing any of them is right.
- **Order**, in a `conflict` case: the newer manual's value comes first.

Values are compared after light clean-up, so `9-11`, `9–11` and `9 to 11 N·m` all count as the same.

### Reading a result

- **`unanswerable` matters most.** A model that answers there has taken a value from the wrong part or the wrong bolt, which is the failure this project exists to prevent (Rule 1).
- **38 cases is a small test.** A gap of one or two cases between two models is not a real difference. A gap of five is.
- **Speed depends on the machine.** Compare the time columns inside one run only. The `Ran on` column says whether Ollama used the GPU or the CPU.
- **`haz-01` was failed by every model.** The warning sits in a different passage from the procedure. The best models repeated the warning but did not cite its passage. This is why `/ask` no longer asks the model for hazards: code attaches them from the hazard list, with their page (ADR 0004, decision 6).

### On real corpus passages

`corpus_questions.json` holds the questions, the pages that answer them and the expected values. It holds no manual text. The cases are built from the index, so the manuals must be indexed first:

```sh
docker compose --profile ingest run --rm -v "$PWD/bench:/bench" ingest \
    python -m app.corpus.cases /bench/corpus_questions.json /bench/data/corpus-cases.json

docker compose --profile bench run --rm llm-bench \
    python run.py --cases data/corpus-cases.json --out data/results
```

`bench/data/` is git-ignored, because the cases and the raw answers contain manual text. Copy only the `.md` summary to `bench/results/` to record a run. A question whose page the search did not return becomes a case the model must abstain on.

### Changing it

- **Add a model**: put its Ollama tag in `BENCH_MODELS`, or in `DEFAULT_MODELS` in `run.py`.
- **Add an invented case**: copy an entry in `cases.json`. `must_include` lists what the answer must contain (a nested list means "any one of these"), `must_exclude` lists values that belong to another part, `cite` lists the passages that hold the answer, and `"ordered": true` makes the order of `must_include` count. For a case with no answer, use `"expect": { "status": "abstained" }`.
- **Change the Ollama version**: set `OLLAMA_VERSION`. A model newer than the Ollama in use refuses to load; the runner reports it and carries on with the others.
