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
| Health    | http://localhost:8000/health | Probes PostgreSQL, Qdrant and MinIO     |
| Qdrant    | http://localhost:6333/dashboard |                                      |
| MinIO     | http://localhost:9001        | `minioadmin` / `minioadmin`             |
| PostgreSQL| localhost:5432               | `repair` / `repair`, database `repair`  |

`minio-init` is a one-shot container that creates the `manuals`, `figures` and
`captures` buckets, then exits — that is expected.

### Local model backend

Ollama is behind the `local` profile so the default stack stays small:

```sh
docker compose --profile local up
docker compose exec ollama ollama pull llama3.2:3b   # once
```

Then set `LLM_BACKEND=local` in `.env` (or switch at runtime as administrator,
US-29).

### Everyday commands

```sh
docker compose up --build          # after changing requirements.txt / package.json
docker compose logs -f backend
docker compose exec backend pytest
docker compose exec backend ruff check .
docker compose down                # keep data
docker compose down -v             # wipe volumes (databases, index, objects)
```

## Layout

```
docker-compose.yml     the stack (T-304)
.env.example           every configurable value, with defaults
backend/               FastAPI service layer (§5)
  app/config.py        settings from the environment
  app/stores.py        PostgreSQL / Qdrant / MinIO clients and probes
  app/contracts.py     the five interface contracts (§5.2, T-202)
  app/routers/api.py   /api/detect, /ask, /figure, /transcribe, /documents
  tests/               contract-shape tests, no stores needed
frontend/              phone-first web client (Vite + React)
infra/postgres/init/   SQL run once on an empty database volume
```

## Working on it

Backend and frontend source directories are bind-mounted, so edits reload
without a rebuild. Model weights, corpora and PDFs are git-ignored: the
manufacturer corpus is never redistributed (§1.4).
