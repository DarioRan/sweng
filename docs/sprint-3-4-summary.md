# Sprints 3–4: what was done for `/ask`, and where to read more

**Milestone M1** (plan §8.1): "a question against the indexed corpus returns a cited, attributed answer, or a correct abstention, with hazards ordered ahead of their steps." **Met** on our 69 labelled questions, with one wrong answer in 41. The independent check is the gold and adversarial sets in Sprint 7.

## Tasks

| Task | What exists now | Read |
|---|---|---|
| T-204 Choose the language model | `qwen3.5:4b`, tested against six other models twice: on fixed passages, then through the whole pipeline | [ADR 0003](adr/0003-local-llm.md) |
| T-203b Index the manuals | 27 manuals indexed: text, page renders, the part codes each manual names, and a searchable description of every figure | [docs/corpus/README.md](corpus/README.md) |
| T-307 Retrieval service | Hybrid search, scoped to the manuals that name the part in the question; the detected component narrows it without blocking it | [ADR 0004](adr/0004-ask-pipeline.md), decisions 1–3 |
| T-502 Confidence and abstention threshold | Threshold 0.75 on the embedder's similarity, chosen on 47 questions and checked on 22 held out; abstains before any model call | ADR 0004, decisions 4–5 |
| T-205 Grounded answering | The model answers from one manual at a time, with the page images, citing a passage on every step | ADR 0004, decision 7 |
| T-501 Specification validator | Every value checked against the cited page; one failure abstains the answer | ADR 0004, decision 8 |
| T-503 Hazard list and safety gate | A list matched against the manual's sentences; warnings attached ahead of their steps, in the manual's words. **The professional-only marks are not authored yet** | ADR 0004, decision 6 |
| T-505 Attribution | Every step, citation and source names its manual and page; no value may come from a non-manufacturer source | ADR 0004, decision 8 |

## Results

69 questions: 41 that the manuals answer, 28 that they do not.

| | `qwen3.5:4b` | Best of the other six models |
|---|---|---|
| Answered correctly | **36 of 41** | 32 |
| Answered wrongly | **1** | 9 |
| Unanswerable questions refused | **28 of 28**, 27 of them with no model call | 27 |
| Seconds per answer (median, RTX 5070) | 1.4 | |

- **Why this model.** Shown a near-miss passage, it says the answer is not there. Asked for a SRAM derailleur torque, three other models gave a Shimano torque and cited it.
- **The one wrong answer.** A real value, printed on the cited page, for another brake lever. No check catches this kind yet ([walk-through](ask-pipeline.md), example 9).
- **A wrong detected component costs nothing.** Given a component that does not match the question, the pipeline still gets 36 right.
- **No reranker.** Five were measured against the embedder's own similarity, and none did better.

## Decisions that changed during the work

1. **The model reads images, but not the user's photo.** The detector names the part in the photograph; the model reads the *manual's* pages, so a table keeps its rows. No fine-tuning: the model follows the manuals because it is shown nothing else and code checks it afterwards.
2. **RAG, not VisRAG.** The manuals have a text layer, and part codes need exact keyword search.
3. **The detected component is a hint, not a filter.** A photograph of the pedals with "the bike barely stops" must still reach the brake manuals. As a hard filter, a wrong component kept 6 of 32 answers; as a hint, 26.
4. **Hazards come from a list, not from the model.** The model cannot leave a warning out, because it is not the one that adds it.
5. **Two manuals that disagree are both reported, newer first.** No model did this when asked in the prompt, so code does it.
6. **The validator abstains instead of stripping values.** This deviates from plan §5.1, stage 7: an answer with its torque removed is no answer.
7. **There is no hosted model.** `LLM_BACKEND` defaults to `local`. US-29 (switch backends) and "latency on both backends" (§7.3) need amending.

## For the team to decide

- [ ] **Which procedures are professional-only** (T-503, US-27). The mechanism is built and tested; the list of marks is empty, because Shimano's manuals do not mark single procedures.
- [ ] **Should Ollama start with the default stack?** `/ask` needs it; it adds about 6 GB to a clean checkout.
- [ ] **Amend the plan** for local-only models (US-29, §7.3) and for the validator abstaining (§5.1).
- [ ] **Accept ADR 0003 and 0004** after a decider reruns the tests (`bench/README.md`).

## Still to do

- **V-brakes.** Download DM-GN0001, re-index, add V-brake questions, and rerun both tests.
- **The independent measurement.** The gold set of 30 and the adversarial set of 20 (T-603, T-604, Sprint 7), written by someone who did not tune the pipeline.
- **Symptom questions** (US-16) score low and are mostly refused.
- **Wiring.** Saving answers to the session, and authentication on the endpoint (T-407, T-402).

## Where everything is

| To… | Read |
|---|---|
| See how a question is answered, with nine real examples | [docs/ask-pipeline.md](ask-pipeline.md) |
| Know why each decision was taken | [docs/adr/README.md](adr/README.md) |
| See every number, or rerun it | [bench/README.md](../bench/README.md), reports in [bench/results/](../bench/results/) |
| Run `/ask` | [README.md](../README.md), "Asking a question" |
| Change the hazard list | [backend/app/rag/hazards.json](../backend/app/rag/hazards.json) |
| Read the code | [backend/app/rag/](../backend/app/rag/): `pipeline.py` holds the order |
