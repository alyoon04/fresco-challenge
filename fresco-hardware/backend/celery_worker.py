"""
Celery worker configuration and task definitions.

Runs the extraction pipeline asynchronously:
  1. ingest_document  — extract text blocks from uploaded PDF
  2. filter_pages     — identify candidate schedule pages
  3. extract_legend   — build per-doc mfr/finish lookup
  4. extract_sets     — run Opus extraction on page batches
  5. reconcile_sets   — merge multi-page sets and snap locations

Usage:
    celery -A celery_worker worker --loglevel=info
"""

from dotenv import load_dotenv
load_dotenv()

import logging
import os
import traceback
import uuid
from pathlib import Path

import anthropic
from celery import Celery
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.extraction.extract import extract_sets_from_pages
from app.extraction.ingest import ingest_document
from app.extraction.legend import extract_legend
from app.extraction.page_filter import filter_pages
from app.extraction.reconcile import reconcile_sets
from app.models.db import (
    ComponentRecord,
    Document,
    DocumentStatus,
    HardwareSetRecord,
    LocationRecord,
    Page,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery app
# ---------------------------------------------------------------------------

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("fresco", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=False,  # Ack immediately so killed tasks don't re-queue on restart
    worker_prefetch_multiplier=1,  # One task at a time (LLM calls are expensive)
    task_default_expires=300,  # Tasks expire after 5 minutes if not picked up
)

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://fresco:fresco@localhost:5432/fresco",
)
_sync_url = DATABASE_URL
if _sync_url.startswith("postgres://"):
    _sync_url = _sync_url.replace("postgres://", "postgresql+psycopg2://", 1)
_sync_url = _sync_url.replace("+asyncpg", "+psycopg2").replace("+aiopg", "+psycopg2")
engine = create_engine(_sync_url)
SessionLocal = sessionmaker(bind=engine)

# Local dev PDF storage
_UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "uploads"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_pdf(doc_id: str) -> bytes:
    """Load PDF bytes from local storage or database."""
    pdf_path = _UPLOAD_DIR / f"{doc_id}.pdf"
    if pdf_path.exists():
        return pdf_path.read_bytes()
    # Fall back to database (deployed environments without shared disk)
    db = SessionLocal()
    try:
        doc = db.get(Document, uuid.UUID(doc_id))
        if doc and doc.pdf_data:
            return doc.pdf_data
    finally:
        db.close()
    raise FileNotFoundError(f"PDF not found for doc {doc_id}")


def _update_status(db, doc_id: str, status: DocumentStatus, error: str | None = None):
    """Update document processing status and notify WebSocket clients."""
    doc = db.get(Document, uuid.UUID(doc_id))
    if doc:
        doc.status = status
        if error is not None:
            doc.error_message = error
        db.commit()

    # Push to WebSocket clients via Redis pub/sub
    try:
        from app.api.routes import publish_status
        publish_status(doc_id, status.value)
    except Exception:
        pass


def _store_sets(db, doc_id: str, sets):
    """Persist a batch of hardware sets to the database."""
    for hw_set in sets:
        set_record = HardwareSetRecord(
            doc_id=uuid.UUID(doc_id),
            set_number=hw_set.set_number,
            description=hw_set.description,
            is_not_used=hw_set.is_not_used,
            overall_confidence=hw_set.overall_confidence,
            column_reasoning=hw_set.column_classification_reasoning,
            raw_json=hw_set.model_dump(),
        )
        db.add(set_record)
        db.flush()

        for idx, comp in enumerate(hw_set.components):
            db_comp = ComponentRecord(
                set_id=set_record.id,
                idx=idx,
                qty=comp.qty,
                description=comp.description.value or "",
                catalog_number=comp.catalog_number.value,
                mfr=comp.mfr.value,
                finish=comp.finish.value,
                notes=comp.notes.value,
                confidences={
                    "description": comp.description.confidence,
                    "catalog_number": comp.catalog_number.confidence,
                    "mfr": comp.mfr.confidence,
                    "finish": comp.finish.confidence,
                    "notes": comp.notes.confidence,
                },
            )
            db.add(db_comp)

        for loc in hw_set.locations:
            db_loc = LocationRecord(
                set_id=set_record.id,
                page_num=loc.page_num,
                bbox=list(loc.bbox) if loc.bbox else None,
                line_start=loc.line_range[0] if loc.line_range else None,
                line_end=loc.line_range[1] if loc.line_range else None,
            )
            db.add(db_loc)

    db.commit()


def _store_results(db, doc_id: str, sets, pages, legend):
    """Persist extraction results to the database."""
    doc = db.get(Document, uuid.UUID(doc_id))
    if not doc:
        return

    doc.legend_json = legend

    for page in pages:
        db_page = Page(
            doc_id=uuid.UUID(doc_id),
            page_num=page.page_num,
            text_blocks=[
                {"text": tb.text, "bbox": list(tb.bbox), "line_idx": tb.line_idx}
                for tb in page.text_blocks
            ],
            is_candidate=False,
            filter_score=0,
        )
        db.add(db_page)

    _store_sets(db, doc_id, sets)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@celery_app.task(name="process_document", bind=True)
def process_document(self, doc_id: str):
    """
    Full extraction pipeline for an uploaded document.

    Stages: ingest → filter → legend → extract → reconcile → store.
    Updates Document.status at each transition. On failure, sets status='failed'
    and stores the traceback in error_message.
    """
    db = SessionLocal()

    try:
        _update_status(db, doc_id, DocumentStatus.PROCESSING)

        # Load PDF
        pdf_bytes = _load_pdf(doc_id)
        logger.info("[%s] Loaded PDF (%d bytes)", doc_id, len(pdf_bytes))

        # Stage 1: Ingest
        pages = ingest_document(pdf_bytes)
        logger.info("[%s] Stage 1: ingested %d pages", doc_id, len(pages))

        # Update page count
        doc = db.get(Document, uuid.UUID(doc_id))
        if doc:
            doc.page_count = len(pages)
            db.commit()

        # Stage 2: Filter
        candidates = filter_pages(pages)
        logger.info("[%s] Stage 2: %d candidate pages", doc_id, len(candidates))

        if not candidates:
            logger.warning("[%s] No candidate pages found — marking done with 0 sets", doc_id)
            _store_results(db, doc_id, [], pages, {"mfr_codes": {}, "finish_codes": {}})
            _update_status(db, doc_id, DocumentStatus.DONE)
            return

        # Stage 3: Legend extraction
        client = anthropic.Anthropic()
        legend = extract_legend(pages, client)
        logger.info(
            "[%s] Stage 3: legend has %d mfr codes, %d finish codes",
            doc_id, len(legend.get("mfr_codes", {})), len(legend.get("finish_codes", {})),
        )

        # Store page data and legend early
        doc = db.get(Document, uuid.UUID(doc_id))
        if doc:
            doc.legend_json = legend
        for page in pages:
            db_page = Page(
                doc_id=uuid.UUID(doc_id),
                page_num=page.page_num,
                text_blocks=[
                    {"text": tb.text, "bbox": list(tb.bbox), "line_idx": tb.line_idx}
                    for tb in page.text_blocks
                ],
                is_candidate=False,
                filter_score=0,
            )
            db.add(db_page)
        db.commit()

        # Stage 4: Extraction with progressive results
        batch_count = [0]

        def _on_batch(batch_sets):
            """Save each batch's sets immediately and notify the frontend."""
            batch_count[0] += 1
            _store_sets(db, doc_id, batch_sets)
            logger.info(
                "[%s] Batch %d complete: +%d sets",
                doc_id, batch_count[0], len(batch_sets),
            )
            try:
                from app.api.routes import publish_status
                publish_status(doc_id, "processing", {"new_sets": len(batch_sets)})
            except Exception:
                pass

        raw_sets = extract_sets_from_pages(pdf_bytes, candidates, legend, client, on_batch=_on_batch)
        logger.info("[%s] Stage 4: extracted %d raw sets", doc_id, len(raw_sets))

        # Stage 5: Reconciliation — merge multi-page sets and snap bboxes
        final_sets = reconcile_sets(raw_sets, pages)
        logger.info("[%s] Stage 5: reconciled to %d sets", doc_id, len(final_sets))

        # Replace progressive results with final reconciled sets (with bboxes)
        db.execute(
            text("DELETE FROM locations WHERE set_id IN (SELECT id FROM hardware_sets WHERE doc_id = :did)"),
            {"did": doc_id},
        )
        db.execute(
            text("DELETE FROM components WHERE set_id IN (SELECT id FROM hardware_sets WHERE doc_id = :did)"),
            {"did": doc_id},
        )
        db.execute(
            text("DELETE FROM hardware_sets WHERE doc_id = :did"),
            {"did": doc_id},
        )
        db.commit()
        _store_sets(db, doc_id, final_sets)

        _update_status(db, doc_id, DocumentStatus.DONE)
        logger.info("[%s] Pipeline complete: %d sets stored", doc_id, len(final_sets))

    except Exception as e:
        logger.error("[%s] Pipeline failed: %s", doc_id, e)
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        _update_status(db, doc_id, DocumentStatus.FAILED, error=error_msg)
        raise
    finally:
        db.close()


@celery_app.task(name="reextract_set", bind=True)
def reextract_set_task(self, doc_id: str, set_id: int, page_nums: list, hint: str = ""):
    """
    Re-extract a specific hardware set from its source pages.

    Used when a user wants to retry extraction with additional guidance.
    The hint string is prepended to the extraction prompt.
    """
    db = SessionLocal()

    try:
        pdf_bytes = _load_pdf(doc_id)
        client = anthropic.Anthropic()

        # Get existing legend
        doc = db.get(Document, uuid.UUID(doc_id))
        legend = doc.legend_json or {"mfr_codes": {}, "finish_codes": {}}

        # Build candidate pages for the target pages only
        pages = ingest_document(pdf_bytes)
        from app.extraction.page_filter import CandidatePage
        candidates = [
            CandidatePage(page_num=pn, full_text=pages[pn].full_text, filter_score=0)
            for pn in page_nums
            if pn < len(pages)
        ]

        # Re-extract
        new_sets = extract_sets_from_pages(pdf_bytes, candidates, legend, client)

        # Find and update the target set
        old_set = db.get(HardwareSetRecord, set_id)
        if old_set and new_sets:
            # Use the first matching set by set_number, or first result
            replacement = next(
                (s for s in new_sets if s.set_number == old_set.set_number),
                new_sets[0],
            )
            old_set.raw_json = replacement.model_dump()
            old_set.overall_confidence = replacement.overall_confidence
            old_set.column_reasoning = replacement.column_classification_reasoning

            # Replace components
            for c in old_set.components:
                db.delete(c)
            for idx, comp in enumerate(replacement.components):
                db.add(ComponentRecord(
                    set_id=set_id,
                    idx=idx,
                    qty=comp.qty,
                    description=comp.description.value or "",
                    catalog_number=comp.catalog_number.value,
                    mfr=comp.mfr.value,
                    finish=comp.finish.value,
                    notes=comp.notes.value,
                    confidences={
                        "description": comp.description.confidence,
                        "catalog_number": comp.catalog_number.confidence,
                        "mfr": comp.mfr.confidence,
                        "finish": comp.finish.confidence,
                        "notes": comp.notes.confidence,
                    },
                ))

            db.commit()
            logger.info("[%s] Re-extracted set %d with %d components", doc_id, set_id, len(replacement.components))

    except Exception as e:
        logger.error("[%s] Re-extraction failed for set %d: %s", doc_id, set_id, e)
        raise
    finally:
        db.close()
