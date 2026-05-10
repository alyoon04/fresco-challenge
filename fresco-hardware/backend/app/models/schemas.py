"""
Pydantic schemas for the extraction pipeline.

These define the structured output format for extracted hardware sets.
All schemas use Pydantic v2 BaseModel with field validators.

Hierarchy:
  HardwareSet
    ├── Location[]       — page + bbox/line_range for each occurrence
    └── Component[]      — individual hardware items (hinge, lockset, etc.)
         └── FieldValue  — extracted string value + confidence score
"""

from typing import List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Leaf types
# ---------------------------------------------------------------------------

class FieldValue(BaseModel):
    """
    A single extracted field with a confidence score.

    `value` is None when the field couldn't be extracted.
    `confidence` is 0.0–1.0 indicating extraction certainty.
    """
    value: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("value", mode="before")
    @classmethod
    def strip_whitespace(cls, v: Optional[str]) -> Optional[str]:
        """Normalize extracted text: strip whitespace, convert empty to None."""
        if v is None:
            return None
        v = v.strip()
        return v if v else None


class Location(BaseModel):
    """
    Where a hardware set appears in the source PDF.

    At least one of `bbox` or `line_range` should be populated.
    Coordinates are in PDF points (72 dpi), origin at top-left.
    """
    page_num: int = Field(ge=1, description="One-indexed page number")
    bbox: Optional[Tuple[float, float, float, float]] = Field(
        default=None,
        description="Bounding box (x0, y0, x1, y1) in PDF points",
    )
    line_range: Optional[Tuple[int, int]] = Field(
        default=None,
        description="Inclusive (start_line, end_line) range",
    )

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v: Optional[Tuple[float, float, float, float]]):
        """Ensure bbox coordinates are non-negative and ordered correctly."""
        if v is not None:
            x0, y0, x1, y1 = v
            if x0 < 0 or y0 < 0 or x1 < 0 or y1 < 0:
                raise ValueError("Bounding box coordinates must be non-negative")
            if x0 > x1 or y0 > y1:
                raise ValueError("Bounding box must have x0<=x1 and y0<=y1")
        return v

    @field_validator("line_range")
    @classmethod
    def validate_line_range(cls, v: Optional[Tuple[int, int]]):
        """Ensure line range start <= end."""
        if v is not None and v[0] > v[1]:
            raise ValueError("line_range start must be <= end")
        return v


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------

class Component(BaseModel):
    """
    One hardware component within a set (e.g., a hinge, lockset, closer).

    `qty` is Optional[int] — output None rather than guessing when missing.
    `description` is required (every component must have one).
    All other fields are FieldValue with optional `value`.
    """
    qty: Optional[int] = Field(default=None, ge=1, description="Quantity (EA). None when not specified — never guess.")
    description: FieldValue = Field(description="Component description (e.g., 'HINGES, FULL MORTISE')")
    catalog_number: FieldValue = Field(default_factory=FieldValue, description="Catalog/model number")
    mfr: FieldValue = Field(default_factory=FieldValue, description="Manufacturer code (e.g., SCH, LCN)")
    finish: FieldValue = Field(default_factory=FieldValue, description="Finish code (e.g., 630, US26D)")
    notes: FieldValue = Field(default_factory=FieldValue, description="Additional notes or remarks")


# ---------------------------------------------------------------------------
# Hardware Set (top-level extraction output)
# ---------------------------------------------------------------------------

class HardwareSet(BaseModel):
    """
    A complete hardware set extracted from a specbook.

    `set_number` is a string — not int — to handle formats like "U-01", "AL 01", "3A".
    `is_not_used` flags sets explicitly marked N/A or NOT USED in the spec.
    `column_classification_reasoning` records how Opus resolved mfr vs. finish columns.
    """
    set_number: str = Field(min_length=1, description="Set identifier (e.g., '1', '3A', 'U-01')")
    description: Optional[str] = Field(default=None, description="Optional heading (e.g., 'ENTRANCE DOORS')")
    locations: List[Location] = Field(default_factory=list, description="Where this set appears in the PDF")
    components: List[Component] = Field(default_factory=list, description="Hardware items in this set")
    is_not_used: bool = Field(default=False, description="True if set is marked N/A or NOT USED")
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Aggregate extraction confidence")
    column_classification_reasoning: Optional[str] = Field(
        default=None,
        description="Opus's explanation of how it classified mfr vs. finish columns",
    )

    @field_validator("set_number", mode="before")
    @classmethod
    def normalize_set_number(cls, v: str) -> str:
        """Strip whitespace from set number."""
        return v.strip()
