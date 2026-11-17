# ADR 0003 — The local language model

- **Status:** Proposed — becomes Accepted when the PR is approved by every decider
- **Date:** 2026-10-13
- **Revised:** 2026-11-16: the candidates were tested again through the whole `/ask` pipeline (ADR 0004). The choice is unchanged and the case for it is much stronger. The rule for manuals that disagree moved to ADR 0004.
- **Deciders:** Sneha Chaudhary, Narmeen Sabah Siddiqui, Dario Ranieri, Yernur Polatbek
- **Issue:** T-204 (choosing the language model)
- **Related:** ADR 0004 (how `/ask` uses the model); `bench/README.md`, which holds the method and the full results of both tests

---

## Context

`/ask` gives a language model the manual passages a search returned and a question. The model must answer from those passages only and cite the passage it used. A wrong torque that looks sourced is the worst outcome this product can have.

**Scope: local models only.** The team decided not to use a hosted model. Every candidate must run offline through Ollama on a team member's machine.

### What the model does and does not do

This decides what to test it on.

| The model does | The model does not |
|---|---|
| Answer from the passages `/ask` gives it, naming the passage each step came from | See the user's photograph. The detector reads it and gives `/ask` a component class (ADR 0002) |
| Read the manual pages as images, so a table keeps its rows | Decide whether to answer. The gate decides first, and abstains without calling the model (ADR 0004) |
| Say so when the passages hold no answer | Write warnings. They come from the hazard list, in the manual's words |
| Describe each manual figure once, at indexing time, so figures can be searched | Have the last word on a value. Code checks every value against the cited page |

The model is not fine-tuned. Only the detector is trained by us.

So the abstention gate removes most questions the manuals cannot answer before the model is involved. What reaches the model is harder: passages that scored well and may still not hold the answer. A page about the same bolt on another caliper. The first page of a procedure whose torque is on the next. The quality that matters most is therefore what the model does with a near miss: say "not here", or answer anyway.

## Candidates

Only models published by a major lab in Ollama's official library, and only their small sizes. No community fine-tunes. All run offline once pulled.

| Model | Lab | Licence shipped with the model | Size | Reads images |
|---|---|---|---|---|
| `qwen3.5:4b` | Alibaba | Apache 2.0 | 3.3 GB | Yes |
| `granite4.2:3b` | IBM | Apache 2.0 | 2.2 GB | No |
| `gemma4:e2b` | Google | Apache 2.0 | 4.6 GB | Yes |
| `phi4-mini` | Microsoft | MIT | 2.5 GB | No |
| `gemma3:4b` | Google | Gemma Terms of Use | 3.4 GB | Yes |
| `qwen2.5:3b` | Alibaba | Qwen Research License (research use only) | 1.9 GB | No |
| `llama3.2:3b` | Meta | Llama 3.2 Community License | 2.0 GB | No |

`llama3.2:3b` was the default before this ADR. Licences were read from the text Ollama stores with each model, on 2026-10-12. "Reads images" is what Ollama reports for the model (`ollama show`), checked on 2026-11-16. Newer Qwen (3.6, 3.8) and Llama (4) exist only at 18 GB and above. `qwen3.5:9b` (6.6 GB) was run as a reference for size.

## Two tests

| | Test 1: fixed passages | Test 2: the whole pipeline |
|---|---|---|
| Date | 2026-10-12 | 2026-11-16 |
| What the model is given | Passages chosen by hand, the same for every model | Whatever the search returns for the question, after the gate |
| Questions | 38 cases: 22 invented, 16 from the real manuals | 69 questions on the real manuals: 41 answerable, 28 not |
| After the model | Nothing | The grounding check, and the comparison of manuals |
| What it measures | The model alone | What the user gets |
| Command | `bench/run.py` | `python -m app.rag.evaluate` |

Both score by fixed rules, with no LLM judge. Test 1 was the basis of this ADR in October. Test 2 exists because test 1 could not rank its two best models, and because the abstention gate changed what the model is asked.

### Test 1: fixed passages

Run of 2026-10-12, Ollama 0.40.3, RTX 4000 Ada. Files: `bench/results/20261012-215558.md` and `20261012-215750-corpus.md`.

| Model | Invented (22) | Real (16) | Both (38) | Invented an answer when there was none (of 9) | Wrong value on real passages (of 11) |
|---|---|---|---|---|---|
| `granite4.2:3b` | 17 | 14 | 31 | 2 | 0 |
| `qwen3.5:4b` | 18 | 12 | **30** | **0** | 1 |
| `gemma4:e2b` | 15 | 12 | 27 | 3 | 1 |
| `phi4-mini` | 15 | 10 | 25 | 3 | 1 |
| `llama3.2:3b` | 12 | 9 | 21 | 4 | 2 |
| `qwen2.5:3b` | 14 | 6 | 20 | 2 | 3 |
| `gemma3:4b` | 13 | 4 | 17 | 4 | 2 |

It separated three weak models from the rest, and showed that `qwen3.5:4b` never invented an answer. It could not separate `qwen3.5:4b` from `granite4.2:3b`: one case apart, on a test where one sentence of the prompt moved single models by up to three cases.

### Test 2: the whole pipeline

Run of 2026-11-16, Ollama 0.40.3, RTX 5070. Threshold 0.75, the same prompt and settings for every model. File: `bench/results/20261116-203244-ask.md`.

- **Right**: answered with the expected value, citing a page that holds it.
- **Wrong**: a wrong value, a page that does not hold the answer, or any answer to an unanswerable question.
- **Lost**: an answerable question the response abstained on.
- **Refused**: unanswerable questions abstained on. 27 of the 28 are stopped by the gate for every model; the last one reaches the model.

A model that reads images was run with two page images and with none. The others ran on text.

| Model | Page images | Right (of 41) | Wrong | Lost | Refused (of 28) | Seconds per answer (median) |
|---|---|---|---|---|---|---|
| **`qwen3.5:4b`** | **2** | **36** | **1** | 4 | **28** | 1.4 |
| `qwen3.5:4b` | 0 | 34 | 2 | 5 | 28 | 0.9 |
| `qwen3.5:9b` (reference) | 0 | 36 | 2 | 3 | 28 | 1.4 |
| `qwen3.5:9b` (reference) | 2 | 34 | 5 | 2 | 28 | 2.5 |
| `gemma4:e2b` | 0 | 32 | 9 | 1 | 27 | 0.6 |
| `granite4.2:3b` | 0 | 28 | 11 | 3 | 27 | 0.7 |
| `gemma4:e2b` | 2 | 27 | 12 | 3 | 27 | 0.8 |
| `phi4-mini` | 0 | 25 | 11 | 5 | 28 | 0.7 |
| `llama3.2:3b` | 0 | 25 | 11 | 5 | 28 | 0.7 |
| `gemma3:4b` | 2 | 23 | 13 | 6 | 27 | 1.7 |
| `gemma3:4b` | 0 | 20 | 19 | 3 | 27 | 0.9 |
| `qwen2.5:3b` | 0 | 18 | 3 | 20 | 28 | 1.4 |

On the 22 questions held out from calibrating the threshold, the order is the same: `qwen3.5:4b` 11 of 13 right and 1 wrong; `granite4.2:3b` 8 and 6; `gemma4:e2b` 10 and 4 at best.

What the results support, and what they do not:

- **Solid: `qwen3.5:4b` gives far fewer wrong answers.** One, against 9 to 19 for the other labs' models. `qwen2.5:3b` gives 3 only because it abstains on half the answerable questions. This is not a one-question gap: it is the difference between a wrong answer in 41 and a wrong answer in 4.
- **Solid: the two models that test 1 could not separate are far apart.** `granite4.2:3b` drops from first to 28 right and 11 wrong. Test 1 gave it passages chosen to hold the answer. The pipeline gives it what a search finds, and when that is a near miss it answers anyway: 5 - 7 N·m, the torque of a different caliper family on a nearby page, where the manual says 8 - 10; a lock ring torque when asked for the tool.
- **Solid: abstention is what separates them.** The one unanswerable question that passes the gate asks for the mounting bolt torque of a SRAM derailleur. `granite4.2:3b`, `gemma4:e2b` and `gemma3:4b` each answered with a torque taken from a Shimano page ("8 - 10 N·m", "6 - 7 N·m", "7.8 - 9.8 N·m") and cited it. `qwen3.5:4b` found no answer in three manuals. This is the behaviour test 1 already showed (0 of 9 against 2 of 9).
- **Solid: twice the size buys nothing here.** `qwen3.5:9b` is level with `qwen3.5:4b` at best, and takes up to twice as long.
- **Not solid: whether page images help.** For `qwen3.5:4b`, two more right and one fewer wrong with images. But a second text-only run of the same model gave 33 right and 3 wrong instead of 34 and 2, so a difference of one or two questions is within what a rerun changes. For `gemma4:e2b` and `qwen3.5:9b`, images made the answers worse. Images are kept on for `qwen3.5:4b` (ADR 0004, decision 1) and are a setting.

## Decision

**`qwen3.5:4b` is the local model**, the default value of `LLM_LOCAL_MODEL`.

In order of weight:

1. **Fewest wrong answers, by a wide margin**, through the pipeline users will actually use: 1 in 41, the next small model 9.
2. **It abstains on a near miss.** It never invented an answer in either test: 0 of 9 on fixed passages, and it refused the one unanswerable question that got past the gate. An unnecessary "I cannot answer that" costs the user a minute. A confident wrong torque can cost a brake.
3. **It reads images.** One model answers from page images and describes the figures for search. `granite4.2:3b`, `phi4-mini` and `llama3.2:3b` cannot.
4. **Licence.** Apache 2.0, with no restriction on use. `qwen2.5:3b` is research-only and `gemma3:4b` has its own terms.
5. **Size and speed.** 3.3 GB: it fits a laptop with 8 GB of memory. 1.4 seconds for an answer on an RTX 5070.
6. **Structured output.** It returned valid JSON in the requested shape in every case of both tests. `qwen2.5:3b` failed to in 19 of the questions of test 2.

**There is no close second.** In October `granite4.2:3b` was the named alternative, worth a second look once abstention was enforced before the model. Abstention now is enforced before the model, and that second look is test 2: it is not an alternative. If more capacity is ever needed, `qwen3.5:9b` is the same family with the same prompt, but it has to earn its place on a larger test first.

## Consequences

- `LLM_LOCAL_MODEL` is `qwen3.5:4b` in `docker-compose.yml`, `.env.example` and `backend/app/config.py`.
- The Ollama image moved from 0.6.8 to 0.40.3: the old version cannot load this model.
- `LLM_BACKEND` now defaults to `local`. There is no hosted model, and `/ask` answers 503 for `hosted`. The administrator's switch between backends (US-29) and "latency on both backends" (plan §7.3) have nothing to switch to or compare with; the plan should be amended, or a hosted backend added later behind the same interface (`app/rag/generation.py`, `VisionModel`).
- The backend calls the model with thinking turned off (`"think": false`). With thinking on, `qwen3.5:4b` took 20 seconds and returned an empty answer.
- Without a GPU it is slow: 10.7 seconds an answer on 24 CPU cores for text alone, measured on 2026-10-12 (`bench/results/20261012-220833-cpu.md`). With page images it will be slower, and it has not been measured. For the offline demonstration on a laptop, set `ASK_PAGE_IMAGES=0` if it is too slow, and measure first.
- The same model describes the figures at indexing time (`app/corpus/captions.py`), so changing the model means describing them again.

## Limits and open items

1. **Both tests are small.** 38 cases and 69 questions separate a model that makes one mistake from models that make ten. They do not measure a difference of one or two.
2. **A rerun is not exactly repeatable.** Temperature 0 and a fixed seed give the same answers on one Ollama instance; across two instances one or two questions changed.
3. **One prompt for every model.** A prompt tuned for another model could raise its score. The prompt was tuned while looking at `qwen3.5:4b`'s failures, which favours it; the size of the gap makes that unlikely to be the whole story.
4. **The questions are ours.** They were written by the person who built the pipeline. The gold set and the adversarial set (T-603, T-604) are the independent measurement.
5. **Tables remain the weak point.** The one wrong answer of `qwen3.5:4b` is a real value from a page about another part (`docs/ask-pipeline.md`, example 9).
6. **CPU speed with page images is not measured**, and the offline demonstration depends on it.
7. **Before Accepted**, a decider reruns test 2 (`bench/README.md`) and checks the table above.
