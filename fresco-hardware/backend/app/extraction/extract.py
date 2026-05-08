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

# TODO: implement extract_sets(), _build_prompt(), _parse_response()
