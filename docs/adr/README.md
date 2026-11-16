# Architecture decision records

One file per decision that would be expensive to change later. Each says what was decided, why, what was measured, and what stays open. A record is **Proposed** until every decider has approved its pull request, then **Accepted**. A later record that replaces it marks it **Superseded**.

| No. | Decision | In one sentence | Status |
|---|---|---|---|
| [0001](0001-public-bicycle-datasets.md) | Public bicycle datasets | DelftBikes is adopted for pretraining only and BIKED is rejected; the detector is trained on our own photographs. | Proposed |
| [0002](0002-component-class-list.md) | The component class list | Twelve drivetrain and brake classes (eleven frozen, `v_brake` added by Amendment 1), the annotation schema and the labels `/api/detect` returns. | Proposed |
| [0003](0003-local-llm.md) | The local language model | `qwen3.5:4b` through Ollama: it abstains when the passages hold no answer, reads page images, and is Apache 2.0. | Proposed |
| [0004](0004-ask-pipeline.md) | How `/ask` answers | Text search scoped by the part named, an abstention gate before any model call, a hazard list, one manual per model call, and a check of every value against the cited page. | Proposed |

## Which record answers which question

| Question | Record |
|---|---|
| Which model answers, and why not a bigger or a hosted one? | 0003 |
| Does the language model see the user's photograph? | 0003, "What the model does and does not do": no, the detector does |
| RAG or VisRAG? Why no reranker? | 0004, decisions 1 and 4 |
| How is the abstention threshold chosen, and what is it? | 0004, decision 5 |
| What if the photograph shows one part and the problem is with another? | 0004, decision 3 |
| What stops the model from inventing a torque? | 0004, decisions 5 and 8 |
| What happens when two manuals disagree? | 0004, decision 7 |
| Where do warnings come from? | 0004, decision 6 |
| Which classes can the detector name? | 0002 |

## Adding a record

1. Copy the header of an existing record: status, date, deciders, issue, related.
2. Number it with the next free number and name the file `NNNN-short-title.md`.
3. Keep the sections: Context, Decision, what was measured, Consequences, Limits and open items.
4. Put numbers in it only if a command in the repository reproduces them, and name the command.
5. Add a row to both tables above.
