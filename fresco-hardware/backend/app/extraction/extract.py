"""
Stage 4: Hardware Set Extraction

Sends batches of schedule pages as text to Claude Sonnet 4.6.
Uses structured output via tool use to return hardware sets, components,
and per-field confidence scores.

Key design decisions:
  - Text mode (not PDF) for speed — 3-5x fewer tokens, much faster
  - 8 parallel batches for throughput
  - on_batch callback for progressive result streaming
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, List, Optional

from app.extraction.page_filter import CandidatePage
from app.models.schemas import HardwareSet

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 16000
_BATCH_SIZE = 4
_MAX_PARALLEL = 8

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "extraction_system.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------

def _build_tool_schema() -> dict:
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
# Batch extraction (text mode)
# ---------------------------------------------------------------------------

def _extract_batch(
    page_texts: dict[int, str],
    legend: dict,
    client: Any,
    tool: dict,
) -> List[HardwareSet]:
    """
    Extract hardware sets from a batch of pages using text input.

    Args:
        page_texts: {original_page_num: full_text} for each page in the batch.
        legend: Per-doc legend dict from Stage 3.
        client: Anthropic client.
        tool: Tool schema dict.

    Returns:
        List of HardwareSet with original page numbers.
    """
    legend_text = ""
    if legend.get("mfr_codes") or legend.get("finish_codes"):
        legend_text = (
            "## Document-specific legend (overrides global reference codes)\n\n"
            f"```json\n{json.dumps(legend, indent=2)}\n```\n\n"
        )

    # Build page text block
    pages_content = ""
    page_nums = sorted(page_texts.keys())
    for pn in page_nums:
        pages_content += f"\n--- Page {pn} ---\n{page_texts[pn]}\n"

    batch_pages_str = ", ".join(str(p) for p in page_nums)
    start_time = time.time()

    response = client.messages.stream(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
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
                "content": (
                    f"{legend_text}"
                    f"Extract all hardware sets from the following specbook pages "
                    f"(page numbers are original document page numbers).\n"
                    f"Use the record_hardware_sets tool to return your results.\n"
                    f"{pages_content}"
                ),
            }
        ],
        tools=[tool],
        tool_choice={"type": "tool", "name": "record_hardware_sets"},
    )

    with response as stream:
        final_message = stream.get_final_message()

    elapsed = time.time() - start_time

    # Log usage metrics
    usage = final_message.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
    total_input = usage.input_tokens
    cache_ratio = cache_read / total_input if total_input > 0 else 0.0
    logger.info(
        "Batch [pages %s] | model=%s | input=%d tokens | output=%d tokens | "
        "cache_read=%d | cache_create=%d | cache_ratio=%.1f%% | latency=%.1fs",
        batch_pages_str, _MODEL, total_input, usage.output_tokens,
        cache_read, cache_create, cache_ratio * 100, elapsed,
    )

    # Parse tool call response
    sets: List[HardwareSet] = []
    for block in final_message.content:
        if block.type == "tool_use" and block.name == "record_hardware_sets":
            raw_sets = block.input.get("hardware_sets", [])
            for raw in raw_sets:
                try:
                    hw_set = HardwareSet.model_validate(raw)
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
    on_batch: Optional[Callable[[List[HardwareSet]], None]] = None,
) -> List[HardwareSet]:
    """
    Extract hardware sets from candidate schedule pages.

    Uses text extraction (not PDF) for speed. Runs up to 8 batches in parallel.
    Calls on_batch(sets) after each batch completes for progressive results.

    Args:
        pdf_bytes: Full original PDF bytes (unused in text mode, kept for API compat).
        candidate_pages: Pages that passed the Stage 2 conjunction filter.
        legend: Per-doc legend from Stage 3.
        anthropic_client: Initialized Anthropic client.
        on_batch: Optional callback invoked with each batch's sets as they complete.

    Returns:
        List of all HardwareSet objects across all batches.
    """
    if not candidate_pages:
        logger.warning("No candidate pages to extract from")
        return []

    sorted_pages = sorted(candidate_pages, key=lambda p: p.page_num)

    logger.info(
        "Extracting from %d candidate pages in batches of %d (max %d parallel)",
        len(sorted_pages), _BATCH_SIZE, _MAX_PARALLEL,
    )

    tool = _build_tool_schema()
    all_sets: List[HardwareSet] = []

    # Prepare batches with 2-page overlap to handle Format D item lists
    # that span multiple pages before the component block
    batches: List[dict[int, str]] = []
    batch_start = 0
    while batch_start < len(sorted_pages):
        batch_end = min(batch_start + _BATCH_SIZE, len(sorted_pages))
        batch_pages = sorted_pages[batch_start:batch_end]
        page_texts = {p.page_num: p.full_text for p in batch_pages}
        batches.append(page_texts)
        batch_start += max(_BATCH_SIZE - 2, 1)

    def _run_batch(page_texts: dict[int, str]):
        page_nums = sorted(page_texts.keys())
        for attempt in range(2):
            try:
                return _extract_batch(page_texts, legend, anthropic_client, tool)
            except Exception as e:
                if attempt == 0:
                    logger.warning(
                        "Batch [pages %s] failed (attempt 1), retrying in 2s: %s",
                        page_nums, e,
                    )
                    time.sleep(2.0)
                else:
                    logger.error(
                        "Batch [pages %s] failed after retry, skipping: %s",
                        page_nums, e,
                    )
        return []

    # Process batches in parallel
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as executor:
        futures = {executor.submit(_run_batch, b): b for b in batches}
        for future in as_completed(futures):
            batch_sets = future.result()
            all_sets.extend(batch_sets)
            if on_batch and batch_sets:
                on_batch(batch_sets)

    logger.info("Extraction complete: %d total sets from %d pages", len(all_sets), len(sorted_pages))
    return all_sets
