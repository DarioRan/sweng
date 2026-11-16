# A Vision-Grounded Repair Assistant

A repair assistant that reads the component in a photograph, answers the
question asked of it from the manufacturer's own manuals, and cites the page it
came from. Validated on bicycle drivetrains and Shimano dealer's manuals.

## Run the stack

Requires Docker Desktop (Windows 11 / macOS) or Docker Engine with the Compose
plugin (Ubuntu 22.04+). Same command everywhere:

```sh
docker compose up
```

Optionally `cp .env.example .env` first to change ports or credentials — every
value has a default, so a clean checkout starts without it.

| Service   | URL                          | Notes                                   |
| --------- | ---------------------------- | --------------------------------------- |
| Web app   | http://localhost:5173        | Vite dev server, hot reload             |
| Backend   | http://localhost:8000/docs   | FastAPI, OpenAPI for the §5.2 contracts |
| Health    | http://localhost:8000/health | Probes PostgreSQL, Qdrant and S3        |
| Qdrant    | http://localhost:6333/dashboard |                                      |
| S3 API    | http://localhost:8333        | SeaweedFS, `repair` / `repair-secret`   |
| Files     | http://localhost:8888        | SeaweedFS file browser, localhost only  |
| PostgreSQL| localhost:5432               | `repair` / `repair`, database `repair`  |

`seaweedfs-init` is a one-shot container that creates the `manuals`, `figures`
and `captures` buckets, then exits — that is expected.

The object store is SeaweedFS behind a plain S3 API. MinIO no longer publishes
public container images, so it cannot be pulled from a clean checkout.

### Asking a question (`/api/ask`)

`/api/ask` answers from the indexed manuals with a local language model, or abstains.
It needs three things that `docker compose up` alone does not give:

```sh
docker compose --profile ingest run --rm ingest          # 1. index data/manuals (docs/corpus/README.md)
docker compose --profile local up -d                     # 2. start Ollama with the stack
docker compose exec ollama ollama pull qwen3.5:4b        # 3. once: the model (ADR 0003), 3.3 GB
docker compose --profile ingest --profile local run --rm ingest python -m app.corpus.captions   # optional: make the figures searchable
```

```sh
curl -s localhost:8000/api/ask -H 'Content-Type: application/json' \
  -d '{"question": "What is the tightening torque for the caliper mounting screw on a BR-R9270?", "job_id": "demo"}'
```

A question the manuals do not cover returns `"status": "abstained"` without calling
the model, so it works even when Ollama is stopped. If Ollama is needed and not
running, `/api/ask` returns 503 and says what to start. How it works, with examples:
[docs/ask-pipeline.md](docs/ask-pipeline.md). Why it works that way:
[ADR 0003](docs/adr/0003-local-llm.md) and [ADR 0004](docs/adr/0004-ask-pipeline.md).

There is no hosted model: the team uses local models only (ADR 0003). With an NVIDIA
GPU, add `-f docker-compose.yml -f docker-compose.gpu.yml` to the commands that start
Ollama (see the notes at the top of `docker-compose.gpu.yml`); an answer then takes
one to two seconds, against ten or more on a CPU.

On a machine with a small disk quota, set the `*_DATA` variables in `.env` to keep the
index, the objects and the model weights in the project folder (`.env.example`).

### Measuring it

Three tests, all described in [bench/README.md](bench/README.md):

```sh
docker compose --profile bench run --rm llm-bench        # models on fixed passages
docker compose --profile ingest run --rm -v "$PWD/bench:/bench" ingest \
    python -m app.rag.calibrate /bench/ask_questions.json --scope /bench/scope_questions.json   # search and threshold
docker compose --profile ingest --profile local run --rm -v "$PWD/bench:/bench" ingest \
    python -m app.rag.evaluate /bench/ask_questions.json                                        # the whole pipeline
```

### Everyday commands

```sh
docker compose up --build          # after changing requirements.txt / package.json
docker compose logs -f backend
docker compose exec backend pytest
docker compose exec backend ruff check .
docker compose --profile ingest run --rm ingest   # index data/manuals (docs/corpus/README.md)
docker compose down                # keep data
docker compose down -v             # wipe volumes (databases, index, objects)
```

## Layout

```
docker-compose.yml     the stack (T-304)
.env.example           every configurable value, with defaults
backend/               FastAPI service layer (§5)
  app/config.py        settings from the environment
  app/stores.py        PostgreSQL / Qdrant / S3 clients and probes
  app/contracts.py     the five interface contracts (§5.2, T-202)
  app/routers/api.py   /api/ask (implemented); /detect, /figure, /transcribe, /documents (stubs)
  app/vision/          frozen component classes, COCO schema (T-306, ADR 0002)
  app/corpus/          manuals to chunks in Qdrant: parse, chunk, embed, index (T-203b)
  app/rag/             /ask: search, abstention gate, safety gate, model, grounding check
  app/rag/hazards.json the hazard list (Rule 3, T-503)
  tests/               contract shapes and the /ask pipeline, no stores or models needed
frontend/              phone-first web client (Vite + React)
infra/postgres/init/   SQL run once on an empty database volume
bench/                 the labelled questions and the three tests of /ask, with results
docs/adr/              decision records (docs/adr/README.md)
docs/ask-pipeline.md   how /ask answers, stage by stage, with examples
docker-compose.gpu.yml optional NVIDIA GPU for Ollama
```

## Working on it

Backend and frontend source directories are bind-mounted, so edits reload
without a rebuild. Model weights, corpora and PDFs are git-ignored: the
manufacturer corpus is never redistributed (§1.4).
