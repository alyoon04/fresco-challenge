"""
Stage 3: Legend Extraction

Scans the document for pages containing explicit manufacturer code lists and
finish code lists. Builds a per-document lookup that overrides global reference
sets during extraction.

Uses Claude Haiku 4.5 (claude-haiku-4-5-20251001) for classification and
extraction of legend entries.

Output: dict with 'mfr_codes' and 'finish_codes' mappings for the document.
"""

# TODO: implement extract_legend(), _find_legend_pages(), _parse_legend()
