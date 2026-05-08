"""
API route tests using FastAPI's TestClient.

Tests run against an in-memory SQLite database (no Postgres required).
Celery tasks are not dispatched — the worker import is mocked.

Since the ORM models use Postgres-specific types (JSONB, UUID, ARRAY), we
monkey-patch SQLAlchemy's SQLite type compiler and UUID type processors to
make them work transparently with SQLite for testing.
"""

import io
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz  # PyMuPDF
import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.pool import StaticPool

# Add backend to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

# ---------------------------------------------------------------------------
# Monkey-patch Postgres types for SQLite compatibility (before any model import)
# ---------------------------------------------------------------------------

import sqlalchemy.dialects.sqlite.base as _sqlite_base
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# DDL: tell SQLite how to render these Postgres column types
_sqlite_base.SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"
_sqlite_base.SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "VARCHAR(36)"
_sqlite_base.SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "JSON"

# DML: UUID bind/result processors — store as plain strings in SQLite
_orig_uuid_bp = PG_UUID.bind_processor
_orig_uuid_rp = PG_UUID.result_processor


def _uuid_bp(self, dialect):
    if dialect.name == "sqlite":
        return lambda v: str(v) if v is not None else None
    return _orig_uuid_bp(self, dialect)


def _uuid_rp(self, dialect, coltype):
    if dialect.name == "sqlite":
        return lambda v: str(v) if v is not None else None
    return _orig_uuid_rp(self, dialect, coltype)


PG_UUID.bind_processor = _uuid_bp
PG_UUID.result_processor = _uuid_rp

# ---------------------------------------------------------------------------
# Now safe to import models
# ---------------------------------------------------------------------------

from sqlalchemy.orm import sessionmaker

from app.models.db import Base

# Single in-memory SQLite engine shared across all tests.
# StaticPool ensures every connection() call returns the same underlying
# SQLite database — without this, each connection gets its own empty DB.
_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(_test_engine)
_TestSession = sessionmaker(bind=_test_engine)


def _make_test_pdf(text: str = "Hardware Set #1\n1 EA HINGE 630 SCH") -> bytes:
    """Create a minimal single-page PDF with the given text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_routes(tmp_path):
    """
    Replace the production DB session and upload dir in the routes module
    with test versions for the duration of each test.
    """
    import app.api.routes as routes_mod

    saved = (routes_mod.engine, routes_mod.SessionLocal, routes_mod._UPLOAD_DIR)

    routes_mod.engine = _test_engine
    routes_mod.SessionLocal = _TestSession
    routes_mod._UPLOAD_DIR = tmp_path

    # Fresh tables each test
    Base.metadata.drop_all(_test_engine)
    Base.metadata.create_all(_test_engine)

    yield

    routes_mod.engine, routes_mod.SessionLocal, routes_mod._UPLOAD_DIR = saved


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.api.routes import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_upload_document(client):
    """POST /api/documents with a valid PDF returns 200 and a doc_id."""
    pdf_bytes = _make_test_pdf()

    with patch.dict("sys.modules", {"celery_worker": MagicMock()}):
        response = client.post(
            "/api/documents",
            files={"file": ("test_spec.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert "doc_id" in data
    assert data["status"] == "uploaded"
    uuid.UUID(data["doc_id"])


def test_upload_rejects_non_pdf(client):
    """POST /api/documents with a non-PDF file returns 400."""
    response = client.post(
        "/api/documents",
        files={"file": ("test.txt", io.BytesIO(b"not a pdf"), "text/plain")},
    )
    assert response.status_code == 400


def test_get_document_after_upload(client):
    """GET /api/documents/{id} returns the document with uploaded status."""
    pdf_bytes = _make_test_pdf()

    with patch.dict("sys.modules", {"celery_worker": MagicMock()}):
        upload_resp = client.post(
            "/api/documents",
            files={"file": ("spec.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

    assert upload_resp.status_code == 200, upload_resp.text
    doc_id = upload_resp.json()["doc_id"]

    get_resp = client.get(f"/api/documents/{doc_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == doc_id
    assert data["status"] in ("uploaded", "UPLOADED")
    assert data["filename"] == "spec.pdf"
    assert data["page_count"] == 1
    assert data["sets"] == []


def test_get_document_not_found(client):
    """GET /api/documents/{id} with a nonexistent ID returns 404."""
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/documents/{fake_id}")
    assert response.status_code == 404


def test_healthz(client):
    """GET /healthz returns a structured response."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data
    assert "db" in data
    assert "redis" in data
