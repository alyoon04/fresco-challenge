# Fresco — Hardware Sets Extractor

Extracts structured hardware sets from Division 08 (Openings) construction specbooks using a 5-stage AI pipeline.

## Architecture

```
PDF Upload → Ingest → Page Filter → Legend Extraction → Set Extraction → Reconciliation → UI
               ↓           ↓              ↓                  ↓               ↓
            PyMuPDF    Conjunction     Haiku 4.5          Opus 4.7      Multi-page
            bboxes      filter        mfr/finish         structured      merge +
                       (regex)        code lookup        tool use       bbox snap
```

## Stack

- **Backend:** FastAPI, Celery, Redis, Postgres, PyMuPDF, Anthropic SDK
- **Frontend:** Next.js 14, react-pdf, Tailwind CSS
- **Storage:** Cloudflare R2 (local volume in dev)
- **Models:** Claude Opus 4.7 (extraction), Claude Haiku 4.5 (legend/classification)

## Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose

### 1. Start infrastructure

```bash
docker compose up -d
```

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your API keys
uvicorn app.api.routes:app --reload
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Celery worker (separate terminal)

```bash
cd backend
celery -A celery_worker worker --loglevel=info
```

## Project Structure

```
backend/
  app/
    api/           → FastAPI route handlers
    extraction/    → 5-stage pipeline (ingest → filter → legend → extract → reconcile)
    models/        → Pydantic schemas + SQLAlchemy ORM
    prompts/       → System prompts for Claude calls
    reference/     → Global mfr/finish code reference lists
frontend/
  app/             → Next.js pages (upload, document review)
  components/      → React components (PDF viewer, set list, detail panel)
scripts/
  eval.py          → Extraction accuracy evaluation
tests/
  fixtures/        → Test PDFs and ground-truth annotations
```
