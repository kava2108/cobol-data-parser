from __future__ import annotations

import re

from .models import PicCategory, PicClause


def _count(s: str, char: str) -> int:
    """Count occurrences of char in a PIC string, expanding (n) repetition notation."""
    total = 0
    pattern = re.compile(rf"{re.escape(char)}(?:\((\d+)\))?", re.IGNORECASE)
    for m in pattern.finditer(s):
        total += int(m.group(1)) if m.group(1) else 1
    return total


def parse_pic(pic_str: str) -> PicClause:
    """Parse a PIC/PICTURE clause value into a PicClause.

    Supports: X (string), 9 (numeric), A (alphabetic), S prefix (signed),
    V (implicit decimal), and (n) repetition notation.
    Falls back to *-edited categories for complex/mixed patterns.
    """
    raw = pic_str
    s = pic_str.upper()

    signed = s.startswith("S")
    body = s[1:] if signed else s

    v_idx = body.find("V")
    has_decimal = v_idx != -1

    if has_decimal:
        int_part = body[:v_idx]
        frac_part = body[v_idx + 1:]
        cat = PicCategory.SIGNED_DECIMAL if signed else PicCategory.DECIMAL
        return PicClause(
            raw=raw,
            category=cat,
            precision=_count(int_part, "9"),
            scale=_count(frac_part, "9"),
        )

    x_count = _count(body, "X")
    a_count = _count(body, "A")
    n_count = _count(body, "9")

    if x_count > 0 and n_count == 0 and a_count == 0:
        return PicClause(raw=raw, category=PicCategory.STRING, length=x_count)

    if a_count > 0 and n_count == 0 and x_count == 0:
        return PicClause(raw=raw, category=PicCategory.ALPHABETIC, length=a_count)

    if n_count > 0 and x_count == 0 and a_count == 0:
        cat = PicCategory.SIGNED_NUMERIC if signed else PicCategory.NUMERIC
        return PicClause(raw=raw, category=cat, length=n_count)

    # Mixed or insertion-edited picture.
    # Presence of X or A means alphanumeric-edited; pure 9s with edit chars → numeric-edited.
    total = x_count + n_count + a_count
    cat = PicCategory.ALPHANUMERIC_EDITED if (x_count > 0 or a_count > 0) else PicCategory.NUMERIC_EDITED
    return PicClause(raw=raw, category=cat, length=total or None)
