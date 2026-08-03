"""Type lowering: resolve a PIC/USAGE pair to a concrete storage byte length.

This is the bridge between the descriptive PIC clause (digit counts,
precision/scale) and the physical layout needed to later decode real
records (DISPLAY text, packed decimal, binary, floating point).
"""
from __future__ import annotations

from typing import Optional

from .models import PicCategory, PicClause

# USAGE values that carry a fixed byte length independent of any PIC clause.
_FIXED_BYTE_LENGTH: dict[str, int] = {
    "COMP-1": 4,
    "COMP-2": 8,
    "INDEX": 4,
    "POINTER": 4,
}

_PACKED_USAGES = {"COMP-3", "PACKED-DECIMAL"}
_BINARY_USAGES = {"COMP", "COMP-4", "COMP-5", "BINARY"}

_TEXT_CATEGORIES = (
    PicCategory.STRING,
    PicCategory.ALPHABETIC,
    PicCategory.ALPHANUMERIC_EDITED,
    PicCategory.NUMERIC_EDITED,
)


def digit_count(pic: PicClause) -> int:
    """Total number of digit positions in a numeric PIC (precision + scale)."""
    if pic.length is not None:
        return pic.length
    return (pic.precision or 0) + (pic.scale or 0)


def _binary_length(digits: int) -> int:
    """IBM COMP/BINARY digit-count tiers: 1-4 -> 2 bytes, 5-9 -> 4, 10-18 -> 8."""
    if digits <= 4:
        return 2
    if digits <= 9:
        return 4
    return 8


def compute_byte_length(
    pic: Optional[PicClause], usage: Optional[str], sign_separate: bool = False
) -> Optional[int]:
    """Resolve the physical storage length, in bytes, for a PIC/USAGE pair.

    Usages without a PIC clause (COMP-1, COMP-2, INDEX, POINTER) get a fixed
    length. Everything else needs a PIC clause to know its size.

    `sign_separate` (SIGN IS ... SEPARATE) adds one extra byte to a DISPLAY
    numeric field, since its sign then occupies its own character position
    instead of being over-punched into a digit byte.
    """
    if usage in _FIXED_BYTE_LENGTH:
        return _FIXED_BYTE_LENGTH[usage]

    if pic is None:
        return None

    if pic.category in _TEXT_CATEGORIES:
        return pic.length

    digits = digit_count(pic)

    if usage in _PACKED_USAGES or pic.category == PicCategory.PACKED_DECIMAL:
        return digits // 2 + 1

    if usage in _BINARY_USAGES or pic.category == PicCategory.BINARY:
        return _binary_length(digits)

    # DISPLAY (default): one byte per digit; sign is over-punched unless SEPARATE.
    return digits + 1 if sign_separate else digits
