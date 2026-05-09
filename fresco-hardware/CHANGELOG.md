# Fresco Hardware Sets Extractor — Development Log

## Architecture

- **Backend**: FastAPI + Celery + PostgreSQL + Redis
- **Frontend**: Next.js 14 (App Router) + TanStack Query + Tailwind + react-pdf
- **Extraction**: Claude Sonnet 4.6 via Anthropic API (structured tool use)
- **Pipeline**: ingest → filter → legend → extract → reconcile → store

---

## Major Changes & Hurdles

### Extraction Pipeline

**Text mode instead of PDF mode**
- Originally sent base64 PDF pages to Claude — slow and token-heavy
- Switched to sending extracted text from PyMuPDF — 3-5x fewer tokens, much faster
- Removed all PDF slicing code; `pdf_bytes` param kept for API compat but unused in text mode

**Parallel batch extraction**
- 8 parallel batches via ThreadPoolExecutor (up from 4 sequential)
- 1-page overlap between batches to avoid splitting sets at boundaries
- Reconciliation deduplicates sets from overlapping batches

**Progressive results**
- Each batch saves sets to DB immediately via `on_batch` callback
- WebSocket push notifies frontend of new sets during processing
- After all batches complete, progressive results are deleted and replaced with final reconciled sets

**Model switch: Opus → Sonnet**
- Switched from `claude-opus-4-7` to `claude-sonnet-4-6` for speed
- Quality is comparable for this structured extraction task

**Streaming required for large outputs**
- Non-streamed requests with `max_tokens > ~10k` were rejected by the SDK
- Switched to `client.messages.stream()` with `stream.get_final_message()`
- `max_tokens` set to 16000

**Temperature parameter removed**
- API started returning 400 for `temperature=0`
- Removed from both `extract.py` and `legend.py`

### Page Filtering

**Broadened filter for diverse formats**
- Original filter only matched "Hardware Group/Set" headers — missed "Item #N" format
- Added `Item` pattern to `_SET_HEADER_RE`
- Added hardware component name patterns (Hinge, Closer, Lock, etc.) to `_QTY_RE`
- Count both mfr AND finish codes (renamed `_count_mfr_codes` → `_count_known_codes`)

**Format D support**
- Added "Item list with shared component block" pattern to extraction prompt
- Example: Item #21, Item #22, ... followed by shared component block = one hardware set
- Model instructed to use first item number as set_number, all items in description

### Location & Highlighting

**Model-reported locations are unreliable**
- The model consistently reports wrong page numbers (off by 1) and line ranges that don't match PyMuPDF's `line_idx` values (model says 1-50, PyMuPDF uses 0-8)
- Multiple attempts at "snapping" model locations to real bboxes failed due to format-specific regex, false positives, and numbering mismatches

**Backend location refinement (`_locate_set`)**
- After reconciliation, search nearby pages (model's pages ±2) for identifying strings
- Constrained to nearby pages to avoid false positives from generic terms matching on unrelated pages (e.g., standards sections early in the PDF)
- Falls back to model's original locations if text search finds nothing

**Frontend: pdf.js text search + DOM span highlighting**
- All page texts indexed once on PDF load via `pdfjs.getTextContent()` — instant search thereafter
- Search terms derived from set description using progressive prefix truncation: "Set: 2.0 — Single Opening – Access Controlled" → try full string, then "Set: 2.0 — Single Opening", then "Set: 2.0" (keeps identifier intact, tries most specific first)
- Highlights rendered by finding matching DOM spans in react-pdf's text layer, computing bounding box, and overlaying a positioned div
- Polls for span dimensions (200ms intervals) since text layer renders asynchronously for distant pages

**What didn't work (and why)**
- Backend-only locations: `_locate_set` searched ALL pages for generic terms, producing false positives on early pages
- Catalog numbers / component descriptions as search terms: these appear in spec/standards sections early in the PDF, not just in hardware set tables
- Short set identifiers ("1.0", "#4"): too generic, match unrelated text everywhere
- Fixed 600ms timeout for text layer render: insufficient for distant pages, spans had zero dimensions
- Index-based span matching (mapping pdf.js text item index to DOM span index): react-pdf DOM structure doesn't match pdf.js item ordering

### Reconciliation

**Batch overlap deduplication**
- Sets extracted from overlapping pages get merged by set_number
- `_sets_overlap()` checks shared pages; `_should_merge()` returns True for overlaps
- `_merge_two_sets()` deduplicates components by (description, catalog_number) and locations by page_num

**Multi-page set merging**
- Sets with same set_number on adjacent pages (gap ≤ 2) merged if continuation has < 3 components
- Preserves first occurrence's description and column reasoning

### Celery / Task Management

**Zombie tasks from Redis**
- Old tasks requeued on worker restart due to `task_acks_late=True`
- Fixed: `task_acks_late=False` (ack immediately), `task_default_expires=300` (5 min TTL)
- Had to purge Redis queue to clear backlog

**Progressive result cleanup**
- After Stage 5 reconciliation, all progressive batch results are deleted from DB
- Final reconciled sets (with correct locations) re-stored
- Prevents duplicates from appearing in the frontend

### Frontend

**No submit button initially**
- `onChange` on file input auto-uploaded — user couldn't review selection
- Added `selectedFile` state + explicit "Upload & Extract" button
- Drag-and-drop also sets `selectedFile` instead of auto-uploading

**WebSocket for real-time updates**
- Replaced polling with WebSocket endpoint `/ws/documents/{doc_id}`
- Redis pub/sub for cross-process notifications (Celery → FastAPI)
- Frontend invalidates TanStack Query cache on WebSocket message
- Required `pip install 'uvicorn[standard]'` for WebSocket support

**PDF viewer**
- Full PDF loaded once, all pages rendered in scrollable container
- Page jump input bar
- Clicking a hardware set scrolls to correct page + highlights bbox
- Highlights use PyMuPDF bboxes scaled to rendered page width

**Hardware set list**
- Sorted by PDF page order (page number, then vertical position)
- Deduplicated by set_number in frontend (safety net)
- Search bar filters by description, component descriptions, catalog numbers, mfr codes
- Description shown as primary label (not set_number — it was confusing)

**Hooks error on `useMemo` after early returns**
- `useMemo` placed after `if (isLoading) return` — hook count changed between renders
- Moved all hooks above early returns

### Database

**Postgres enum case mismatch**
- Python enum values were uppercase ('UPLOADED'), Postgres expected lowercase ('uploaded')
- Fixed with `values_callable=lambda e: [x.value for x in e]` on the Enum column

### Config

**TypeScript target deprecation**
- `target: "es5"` produced deprecation warning in Next.js 14
- Changed to `target: "es6"` in `tsconfig.json`

**Environment setup**
- Added `dotenv` loading at top of both `celery_worker.py` and `app/api/routes.py`
- Created `.env.example` files for both backend and frontend
