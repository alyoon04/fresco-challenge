# Fresco Hardware Sets Extractor

Extracts hardware sets from Division 08 (Openings) construction specification PDFs into structured data with page locations, confidence scores, and an interactive review UI.

## Architecture

- **Backend**: FastAPI + Celery + PostgreSQL + Redis
- **Frontend**: Next.js 14 (App Router) + TanStack Query + Tailwind + react-pdf
- **Extraction**: Claude Sonnet 4.6 via Anthropic API (structured tool use)
- **Pipeline**: ingest → filter → legend → extract → reconcile → store

## Quick Start (Docker)

```bash
# 1. Start Postgres + Redis
docker-compose up -d

# 2. Backend
cd backend
cp .env.example .env          # add your ANTHROPIC_API_KEY
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # run migrations
uvicorn app.api.routes:app --reload &
celery -A celery_worker worker --loglevel=info &

# 3. Frontend
cd ../frontend
cp .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000), upload a spec PDF, and watch extraction run in real time.

## Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 16 (or use Docker)
- Redis 7 (or use Docker)
- Anthropic API key

## Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` from the example and fill in your API key:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (required) | — |
| `DATABASE_URL` | Postgres connection string | `postgresql+psycopg2://fresco:fresco@localhost:5432/fresco` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `UPLOAD_DIR` | Local PDF storage directory | `uploads` |

Run database migrations:

```bash
alembic upgrade head
```

Start the API server and Celery worker (two separate terminals):

```bash
# Terminal 1 — API
uvicorn app.api.routes:app --reload --port 8000

# Terminal 2 — Worker
celery -A celery_worker worker --loglevel=info
```

## Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

| Variable | Description | Default |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `http://localhost:8000` |

## Extraction Pipeline

The pipeline runs as a Celery task with 5 stages:

1. **Ingest** — PyMuPDF extracts text blocks with bounding boxes from every page.
2. **Filter** — Structural heuristics identify candidate hardware schedule pages (set headers, quantity patterns, known manufacturer/finish codes). Reduces 600+ page specs to ~20-50 relevant pages.
3. **Legend** — Claude Haiku extracts per-document manufacturer and finish code legends from candidate pages, overriding global reference codes.
4. **Extract** — Claude Sonnet 4.6 processes pages in parallel batches (8 concurrent, 1-page overlap) using structured tool use. Progressive results pushed to frontend via WebSocket.
5. **Reconcile** — Merges multi-page sets, deduplicates batch overlaps, and refines page locations by searching nearby pages for identifying text.

## Key Features

- **Multi-format support** — Handles explicit column headers (Format A), implicit columns (Format B), tabular schedules (Format C), and item-list-with-shared-component-block (Format D).
- **Mfr vs finish disambiguation** — Column-level majority-rule classification. Ambiguous codes like "PE" (Pemko or Painted Enamel) resolved by surrounding column context. Reasoning stored per set.
- **Confidence scores** — Per-field confidence (0.0–1.0) with color-coded display. Lower scores for inferred positions, ambiguous codes, OCR degradation.
- **Feedback UI** — Click any extracted field to correct it. Corrections saved with audit trail.
- **PDF navigation** — Click a hardware set to scroll to its location in the PDF with text highlighting.
- **Real-time progress** — WebSocket pushes progressive results during extraction.
- **Legend resolution** — Per-document code lookup tables extracted and applied automatically.
- **NOT USED sets** — Detected and displayed with visual badge.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/documents` | Upload PDF, queue extraction |
| `GET` | `/api/documents` | List all documents |
| `GET` | `/api/documents/{id}` | Document metadata + all sets |
| `GET` | `/api/documents/{id}/pdf` | Stream full PDF |
| `GET` | `/api/documents/{id}/page/{n}` | Stream single page |
| `PATCH` | `/api/sets/{id}/components/{idx}` | Correct an extracted field |
| `POST` | `/api/sets/{id}/reextract` | Re-run extraction with hint |
| `GET` | `/api/reference/mfr_codes` | Global manufacturer codes |
| `GET` | `/api/reference/finish_codes` | Global finish codes |
| `GET` | `/healthz` | Health check (DB + Redis) |
| `WS` | `/ws/documents/{id}` | Real-time status updates |

## Project Structure

```
backend/
  app/
    api/routes.py          # FastAPI endpoints + WebSocket
    extraction/
      ingest.py            # Stage 1: PDF text extraction
      page_filter.py       # Stage 2: candidate page filtering
      legend.py            # Stage 3: legend extraction
      extract.py           # Stage 4: LLM hardware set extraction
      reconcile.py         # Stage 5: merge + deduplicate + locate
    models/
      db.py                # SQLAlchemy ORM models
      schemas.py           # Pydantic schemas (FieldValue, Component, HardwareSet)
    prompts/
      extraction_system.txt  # Extraction prompt (Format A/B/C/D, examples)
      legend_system.txt      # Legend extraction prompt
    reference/
      mfr_codes.json       # Global manufacturer code reference
      finish_codes.json    # Global finish code reference
  celery_worker.py         # Celery task orchestration
  alembic/                 # Database migrations

frontend/
  app/
    page.tsx               # Upload + document list
    doc/[id]/page.tsx       # Three-pane document viewer
    api.ts                 # API client + types
  components/
    PdfViewer.tsx           # PDF rendering + search + highlight
    SetList.tsx             # Hardware set sidebar with search
    ComponentTable.tsx      # Editable component table with confidence
    ReextractButton.tsx     # Re-extraction trigger
```
