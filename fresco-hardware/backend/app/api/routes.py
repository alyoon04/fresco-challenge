"""
FastAPI route definitions for the Fresco extraction service.

Endpoints:
  POST   /api/documents                              Upload PDF, queue extraction
  GET    /api/documents/{doc_id}                      Document metadata + sets
  GET    /api/documents/{doc_id}/page/{page_num}      Stream a single PDF page
  PATCH  /api/sets/{set_id}/components/{comp_idx}     Correct an extracted field
  POST   /api/sets/{set_id}/reextract                 Re-run extraction with hint
  GET    /api/reference/mfr_codes                     Global manufacturer codes
  GET    /api/reference/finish_codes                  Global finish codes
  GET    /healthz                                     Health check
"""

from dotenv import load_dotenv
load_dotenv()

import io
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

import asyncio

import fitz  # PyMuPDF
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.models.db import (
    Base,
    ComponentRecord,
    Correction,
    Document,
    DocumentStatus,
    HardwareSetRecord,
    LocationRecord,
    Page,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Fresco Hardware Sets API",
    description="Extract and review hardware sets from Division 08 specbooks",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Database setup (sync engine for API routes — async can be added later)
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://fresco:fresco@localhost:5432/fresco",
)
# Normalize async driver to sync for the API's synchronous session
_sync_url = DATABASE_URL.replace("+asyncpg", "+psycopg2").replace("+aiopg", "+psycopg2")

engine = create_engine(_sync_url)
SessionLocal = sessionmaker(bind=engine)

# Local dev PDF storage fallback (used when R2 is not configured)
_UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "uploads"))
_UPLOAD_DIR.mkdir(exist_ok=True)


def _get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    doc_id: str
    status: str


class FieldCorrection(BaseModel):
    field: str    # "mfr", "finish", "description", "catalog_number", "notes"
    value: str


class ReextractRequest(BaseModel):
    hint: str = ""


class HealthResponse(BaseModel):
    ok: bool
    db: str
    redis: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pdf_path(doc_id: str) -> Path:
    """Local filesystem path for a document's PDF (dev mode)."""
    return _UPLOAD_DIR / f"{doc_id}.pdf"


def _serialize_set(row: HardwareSetRecord) -> dict:
    """Serialize a HardwareSetRecord to a JSON-safe dict."""
    return {
        "id": row.id,
        "set_number": row.set_number,
        "description": row.description,
        "is_not_used": row.is_not_used,
        "overall_confidence": row.overall_confidence,
        "column_reasoning": row.column_reasoning,
        "components": [
            {
                "idx": c.idx,
                "qty": c.qty,
                "description": c.description,
                "catalog_number": c.catalog_number,
                "mfr": c.mfr,
                "finish": c.finish,
                "notes": c.notes,
                "confidences": c.confidences,
            }
            for c in sorted(row.components, key=lambda c: c.idx)
        ],
        "locations": [
            {
                "page_num": loc.page_num,
                "bbox": loc.bbox,
                "line_start": loc.line_start,
                "line_end": loc.line_end,
            }
            for loc in row.locations
        ],
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/healthz", response_model=HealthResponse)
def healthz():
    """Health check — verify DB and Redis connectivity."""
    db_status = "down"
    redis_status = "down"

    # Check DB
    try:
        db = _get_db()
        db.execute(text("SELECT 1"))
        db_status = "up"
        db.close()
    except Exception:
        pass

    # Check Redis
    try:
        import redis as redis_lib
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis_lib.from_url(redis_url)
        r.ping()
        redis_status = "up"
    except Exception:
        pass

    return HealthResponse(
        ok=(db_status == "up"),
        db=db_status,
        redis=redis_status,
    )


@app.get("/api/documents")
def list_documents():
    """List all documents, most recent first."""
    db = _get_db()
    try:
        docs = db.execute(
            select(Document).order_by(Document.created_at.desc())
        ).scalars().all()
        return [
            {
                "id": str(d.id),
                "filename": d.filename,
                "page_count": d.page_count,
                "status": d.status.value if hasattr(d.status, "value") else d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "set_count": len(d.hardware_sets),
            }
            for d in docs
        ]
    finally:
        db.close()


@app.post("/api/documents", response_model=UploadResponse)
def upload_document(file: UploadFile = File(...)):
    """
    Upload a PDF specbook and queue it for extraction.

    Stores the PDF locally (dev) or to R2 (prod), creates a Document row,
    and dispatches a Celery task to process it.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    pdf_bytes = file.file.read()
    if len(pdf_bytes) == 0:
        raise HTTPException(400, "Empty file")

    doc_id = str(uuid.uuid4())
    r2_key = f"documents/{doc_id}/{file.filename}"

    # Store locally in dev
    pdf_path = _pdf_path(doc_id)
    pdf_path.write_bytes(pdf_bytes)

    # Count pages
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(doc)
        doc.close()
    except Exception:
        page_count = 0

    # Create DB record
    db = _get_db()
    try:
        db_doc = Document(
            id=doc_id,
            filename=file.filename,
            r2_key=r2_key,
            page_count=page_count,
            status=DocumentStatus.UPLOADED,
        )
        db.add(db_doc)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Failed to create document record: {e}")
    finally:
        db.close()

    # Queue Celery task (import here to avoid circular import at module load)
    try:
        from celery_worker import process_document
        process_document.delay(doc_id)
    except Exception as e:
        logger.warning("Failed to queue Celery task (worker may be offline): %s", e)

    return UploadResponse(doc_id=doc_id, status="uploaded")


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    """
    Get document metadata, processing status, and extracted hardware sets.

    Returns all sets with components and locations if status is 'done'.
    """
    db = _get_db()
    try:
        doc = db.execute(
            select(Document).where(Document.id == doc_id)
        ).scalar_one_or_none()
        if not doc:
            raise HTTPException(404, "Document not found")

        result = {
            "id": str(doc.id),
            "filename": doc.filename,
            "page_count": doc.page_count,
            "status": doc.status.value if hasattr(doc.status, "value") else doc.status,
            "error_message": getattr(doc, "error_message", None),
            "legend": doc.legend_json,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "sets": [_serialize_set(s) for s in doc.hardware_sets],
        }
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        db.close()


@app.get("/api/documents/{doc_id}/pdf")
def get_full_pdf(doc_id: str):
    """Stream the full PDF for the frontend viewer."""
    pdf_path = _pdf_path(doc_id)
    if not pdf_path.exists():
        raise HTTPException(404, "PDF file not found")
    return StreamingResponse(
        open(pdf_path, "rb"),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={doc_id}.pdf"},
    )


@app.get("/api/documents/{doc_id}/page/{page_num}")
def get_page_pdf(doc_id: str, page_num: int):
    """
    Stream a single PDF page for the frontend PDF viewer.

    Returns a minimal PDF containing just the requested page.
    """
    pdf_path = _pdf_path(doc_id)
    if not pdf_path.exists():
        raise HTTPException(404, "PDF file not found")

    try:
        src = fitz.open(str(pdf_path))
        if page_num < 0 or page_num >= len(src):
            src.close()
            raise HTTPException(400, f"Page {page_num} out of range (0-{len(src)-1})")

        # Create single-page PDF
        dst = fitz.open()
        dst.insert_pdf(src, from_page=page_num, to_page=page_num)
        page_bytes = dst.tobytes()
        dst.close()
        src.close()

        return StreamingResponse(
            io.BytesIO(page_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=page_{page_num}.pdf"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to extract page: {e}")


@app.patch("/api/sets/{set_id}/components/{component_idx}")
def correct_component(set_id: int, component_idx: int, body: FieldCorrection):
    """
    Apply a user correction to a single field of a component.

    Writes to the Correction table for audit trail AND updates the canonical
    ComponentRecord so subsequent reads reflect the fix.
    """
    valid_fields = {"description", "catalog_number", "mfr", "finish", "notes"}
    if body.field not in valid_fields:
        raise HTTPException(400, f"Invalid field '{body.field}'. Must be one of: {valid_fields}")

    db = _get_db()
    try:
        # Find the component
        comp = db.execute(
            select(ComponentRecord).where(
                ComponentRecord.set_id == set_id,
                ComponentRecord.idx == component_idx,
            )
        ).scalar_one_or_none()

        if not comp:
            raise HTTPException(404, f"Component not found: set_id={set_id}, idx={component_idx}")

        original_value = getattr(comp, body.field)

        # Record the correction
        correction = Correction(
            set_id=set_id,
            component_idx=component_idx,
            field_name=body.field,
            original_value=original_value,
            corrected_value=body.value,
        )
        db.add(correction)

        # Update the canonical record
        setattr(comp, body.field, body.value)

        db.commit()
        return {"ok": True, "field": body.field, "old": original_value, "new": body.value}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))
    finally:
        db.close()


@app.post("/api/sets/{set_id}/reextract")
def reextract_set(set_id: int, body: ReextractRequest):
    """
    Re-run extraction on the pages associated with a hardware set.

    Optionally accepts a hint string that gets prepended to the extraction
    prompt to guide the model (e.g., "This set uses Format B with implicit columns").
    """
    db = _get_db()
    try:
        hw_set = db.execute(
            select(HardwareSetRecord).where(HardwareSetRecord.id == set_id)
        ).scalar_one_or_none()
        if not hw_set:
            raise HTTPException(404, "Hardware set not found")

        # Get the document and page numbers for this set
        doc = hw_set.document
        page_nums = [loc.page_num for loc in hw_set.locations]

        if not page_nums:
            raise HTTPException(400, "Set has no associated page locations")

        # Queue a targeted re-extraction Celery task
        try:
            from celery_worker import reextract_set_task
            reextract_set_task.delay(
                str(doc.id), set_id, page_nums, body.hint,
            )
        except Exception as e:
            logger.warning("Failed to queue reextract task: %s", e)
            raise HTTPException(503, "Worker unavailable")

        return {"ok": True, "set_id": set_id, "pages": page_nums, "hint": body.hint}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

_REF_DIR = Path(__file__).resolve().parent.parent / "reference"


@app.get("/api/reference/mfr_codes")
def get_mfr_codes():
    """Return global manufacturer code reference list."""
    with open(_REF_DIR / "mfr_codes.json") as f:
        return json.load(f)


@app.get("/api/reference/finish_codes")
def get_finish_codes():
    """Return global finish code reference list."""
    with open(_REF_DIR / "finish_codes.json") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# WebSocket — push document status updates via Redis pub/sub
# ---------------------------------------------------------------------------

def publish_status(doc_id: str, status: str, extra: dict | None = None):
    """Publish a status change to Redis so WebSocket clients get notified.

    Call this from the Celery worker whenever Document.status changes.
    """
    try:
        import redis as redis_lib
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis_lib.from_url(redis_url)
        payload = json.dumps({"status": status, **(extra or {})})
        r.publish(f"doc:{doc_id}", payload)
    except Exception:
        pass  # Redis down — clients fall back to polling


@app.websocket("/ws/documents/{doc_id}")
async def ws_document_status(ws: WebSocket, doc_id: str):
    """Stream document status updates to the frontend.

    Sends the current status on connect, then pushes Redis pub/sub messages
    until the client disconnects or status reaches a terminal state.
    """
    await ws.accept()

    # Send current status immediately
    db = _get_db()
    try:
        doc = db.execute(
            select(Document).where(Document.id == doc_id)
        ).scalar_one_or_none()
        if doc:
            status_val = doc.status.value if hasattr(doc.status, "value") else doc.status
            await ws.send_json({"status": status_val})
            if status_val in ("done", "failed"):
                await ws.close()
                return
    finally:
        db.close()

    # Subscribe to Redis channel for this document
    try:
        import redis as redis_lib
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis_lib.from_url(redis_url)
        pubsub = r.pubsub()
        pubsub.subscribe(f"doc:{doc_id}")
    except Exception:
        # No Redis — fall back to simple polling loop
        try:
            while True:
                await asyncio.sleep(3)
                db = _get_db()
                try:
                    doc = db.execute(
                        select(Document).where(Document.id == doc_id)
                    ).scalar_one_or_none()
                    if doc:
                        status_val = doc.status.value if hasattr(doc.status, "value") else doc.status
                        await ws.send_json({"status": status_val})
                        if status_val in ("done", "failed"):
                            break
                finally:
                    db.close()
        except WebSocketDisconnect:
            pass
        return

    # Listen for pub/sub messages
    try:
        while True:
            msg = await asyncio.to_thread(pubsub.get_message, ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg["type"] == "message":
                data = json.loads(msg["data"])
                await ws.send_json(data)
                if data.get("status") in ("done", "failed"):
                    break
    except WebSocketDisconnect:
        pass
    finally:
        pubsub.unsubscribe()
        pubsub.close()
