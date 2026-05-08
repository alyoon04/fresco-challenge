"""
Stage 4: Hardware Set Extraction

Sends batches of 3-5 schedule pages to Claude Opus 4.7 (claude-opus-4-7) using
native PDF input. Uses structured output via tool use to return hardware sets,
components, and per-field confidence scores.

Key responsibility: manufacturer vs. finish column disambiguation.
  - Classifies columns by majority membership in known mfr/finish reference sets
  - Per-doc legend (from Stage 3) overrides global reference codes
  - Records reasoning in column_classification_reasoning field

Handles three observed formats:
  1. ATC-style:       Explicit column headers under "Hardware Group No. XX"
  2. Hdw_Spec-style:  "Set #N" header + implicit-column list lines
  3. Pure tabular:    Rows grouped under set headers in a table schedule
"""

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any, List

import fitz  # PyMuPDF

from app.extraction.page_filter import CandidatePage
from app.models.schemas import HardwareSet

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OPUS_MODEL = "claude-opus-4-7"
_MAX_TOKENS = 8000
_BATCH_SIZE = 4

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "extraction_system.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------

def _build_tool_schema() -> dict:
    """
    Build the tool definition for record_hardware_sets.

    Wraps HardwareSet's JSON schema in a list so the model can return
    multiple sets in a single tool call.
    """
    set_schema = HardwareSet.model_json_schema()
    return {
        "name": "record_hardware_sets",
        "description": (
            "Record all hardware sets found on the provided specbook pages. "
            "Call this tool exactly once with every set found."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hardware_sets": {
                    "type": "array",
                    "items": set_schema,
                    "description": "List of all hardware sets extracted from the pages.",
                }
            },
            "required": ["hardware_sets"],
        },
    }


# ---------------------------------------------------------------------------
# PDF slicing
# ---------------------------------------------------------------------------

def _slice_pdf(pdf_bytes: bytes, page_indices: List[int]) -> bytes:
    """
    Create a new PDF containing only the specified pages from the original.

    Args:
        pdf_bytes: Original full PDF bytes.
        page_indices: Zero-indexed page numbers to include.

    Returns:
        Bytes of the sliced PDF.
    """
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    dst = fitz.open()  # New empty PDF
    for idx in page_indices:
        dst.insert_pdf(src, from_page=idx, to_page=idx)
    result = dst.tobytes()
    dst.close()
    src.close()
    return result


# ---------------------------------------------------------------------------
# Batch extraction
# ---------------------------------------------------------------------------

def _extract_batch(
    batch_pdf_bytes: bytes,
    page_mapping: dict[int, int],
    legend: dict,
    client: Any,
    tool: dict,
) -> List[HardwareSet]:
    """
    Extract hardware sets from a single batch of pages.

    Args:
        batch_pdf_bytes: PDF bytes containing only this batch's pages.
        page_mapping: {batch_page_idx: original_page_num} for location translation.
        legend: Per-doc legend dict from Stage 3.
        client: Anthropic client.
        tool: Tool schema dict.

    Returns:
        List of HardwareSet with page numbers translated to original doc coordinates.
    """
    pdf_b64 = base64.standard_b64encode(batch_pdf_bytes).decode("ascii")

    # Build user message: legend context + PDF document
    legend_text = ""
    if legend.get("mfr_codes") or legend.get("finish_codes"):
        legend_text = (
            "## Document-specific legend (overrides global reference codes)\n\n"
            f"```json\n{json.dumps(legend, indent=2)}\n```\n\n"
        )

    batch_pages_str = ", ".join(str(v) for v in sorted(page_mapping.values()))

    start_time = time.time()

    response = client.messages.create(
        model=_OPUS_MODEL,
        max_tokens=_MAX_TOKENS,
        temperature=0,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"{legend_text}"
                            f"Extract all hardware sets from the following specbook pages "
                            f"(original page numbers: {batch_pages_str}). "
                            f"Use the record_hardware_sets tool to return your results."
                        ),
                    },
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                ],
            }
        ],
        tools=[tool],
        tool_choice={"type": "tool", "name": "record_hardware_sets"},
    )

    elapsed = time.time() - start_time

    # Log usage metrics
    usage = response.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
    total_input = usage.input_tokens
    cache_ratio = cache_read / total_input if total_input > 0 else 0.0
    logger.info(
        "Batch [pages %s] | model=%s | input=%d tokens | output=%d tokens | "
        "cache_read=%d | cache_create=%d | cache_ratio=%.1f%% | latency=%.1fs",
        batch_pages_str, _OPUS_MODEL, total_input, usage.output_tokens,
        cache_read, cache_create, cache_ratio * 100, elapsed,
    )

    # Parse tool call response
    sets: List[HardwareSet] = []
    for block in response.content:
        if block.type == "tool_use" and block.name == "record_hardware_sets":
            raw_sets = block.input.get("hardware_sets", [])
            for raw in raw_sets:
                try:
                    hw_set = HardwareSet.model_validate(raw)
                    # Translate batch-relative page numbers to original doc page numbers
                    for loc in hw_set.locations:
                        original = page_mapping.get(loc.page_num, loc.page_num)
                        loc.page_num = original
                    sets.append(hw_set)
                except Exception as e:
                    logger.warning("Failed to parse hardware set: %s — raw: %s", e, raw)

    logger.info("Batch [pages %s] extracted %d sets", batch_pages_str, len(sets))
    return sets


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_sets_from_pages(
    pdf_bytes: bytes,
    candidate_pages: List[CandidatePage],
    legend: dict,
    anthropic_client: Any,
) -> List[HardwareSet]:
    """
    Extract hardware sets from candidate schedule pages using Claude Opus 4.7.

    Algorithm:
      1. Slice original PDF to only candidate pages, keeping page number mapping.
      2. Group candidate pages into batches of 4.
      3. For each batch, create a batch PDF and send to Opus with the extraction
         system prompt (cached), legend context, and PDF as a document block.
      4. Parse tool-use responses into HardwareSet objects, translating page numbers.
      5. Retry once on API failure; on second failure, log and skip the batch.

    Args:
        pdf_bytes: Full original PDF bytes.
        candidate_pages: Pages that passed the Stage 2 conjunction filter.
        legend: Per-doc legend from Stage 3 {"mfr_codes": {...}, "finish_codes": {...}}.
        anthropic_client: Initialized Anthropic client.

    Returns:
        List of HardwareSet objects across all batches.
    """
    if not candidate_pages:
        logger.warning("No candidate pages to extract from")
        return []

    # Sort by page number for consistent ordering
    sorted_pages = sorted(candidate_pages, key=lambda p: p.page_num)
    page_indices = [p.page_num for p in sorted_pages]

    logger.info(
        "Extracting from %d candidate pages in batches of %d",
        len(page_indices), _BATCH_SIZE,
    )

    tool = _build_tool_schema()
    all_sets: List[HardwareSet] = []

    # Process in batches
    for batch_start in range(0, len(page_indices), _BATCH_SIZE):
        batch_indices = page_indices[batch_start : batch_start + _BATCH_SIZE]

        # Build mapping: position in batch PDF → original page number
        page_mapping = {i: orig for i, orig in enumerate(batch_indices)}

        # Slice the original PDF to just this batch's pages
        batch_pdf = _slice_pdf(pdf_bytes, batch_indices)

        # Attempt extraction with one retry
        for attempt in range(2):
            try:
                batch_sets = _extract_batch(
                    batch_pdf, page_mapping, legend, anthropic_client, tool,
                )
                all_sets.extend(batch_sets)
                break
            except Exception as e:
                if attempt == 0:
                    wait = 2.0
                    logger.warning(
                        "Batch [pages %s] failed (attempt 1), retrying in %.0fs: %s",
                        batch_indices, wait, e,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "Batch [pages %s] failed after retry, skipping: %s",
                        batch_indices, e,
                    )

    logger.info("Extraction complete: %d total sets from %d pages", len(all_sets), len(page_indices))
    return all_sets
