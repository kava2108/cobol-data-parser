from __future__ import annotations

import re

from .models import PicCategory, PicClause


_REPEAT_RE = re.compile(r"\((\d+)\)")

# Insertion/editing symbols (COBOL PICTURE editing): zero suppression (Z, *),
# insertion (B, 0, /, comma, period), sign (+, -, CR, DB), currency ($).
_EDIT_SYMBOL_CHARS = set("ZB0/,.+-$*")


def _count(s: str, char: str) -> int:
    """Count occurrences of char in a PIC string, expanding (n) repetition notation."""
    total = 0
    pattern = re.compile(rf"{re.escape(char)}(?:\((\d+)\))?", re.IGNORECASE)
    for m in pattern.finditer(s):
        total += int(m.group(1)) if m.group(1) else 1
    return total


def _has_edit_symbols(body: str) -> bool:
    stripped = _REPEAT_RE.sub("", body)
    if "CR" in stripped or "DB" in stripped:
        return True
    return any(ch in _EDIT_SYMBOL_CHARS for ch in stripped)


def _tokenize_edited(body: str) -> list[tuple[str, int]]:
    """Tokenize an edited PIC clause body into (symbol, display-width) pairs."""
    tokens: list[tuple[str, int]] = []
    i, n = 0, len(body)
    while i < n:
        two = body[i:i + 2]
        if two in ("CR", "DB"):
            tokens.append((two, 2))
            i += 2
            continue
        ch = body[i]
        if ch not in "9XAZB0/,.+-$*":
            i += 1
            continue
        i += 1
        count = 1
        m = _REPEAT_RE.match(body, i)
        if m:
            count = int(m.group(1))
            i = m.end()
        tokens.append((ch, count))
    return tokens


def parse_pic(pic_str: str) -> PicClause:
    """Parse a PIC/PICTURE clause value into a PicClause.

    Supports: X (string), 9 (numeric), A (alphabetic), S prefix (signed),
    V (implicit decimal), and (n) repetition notation.
    Falls back to *-edited categories for complex/mixed or insertion-edited
    patterns (Z, *, B, 0, /, comma, period, +/-, CR/DB, $), capturing the
    distinct editing symbols present and the total display width.
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
    edited = _has_edit_symbols(body)

    if x_count > 0 and n_count == 0 and a_count == 0 and not edited:
        return PicClause(raw=raw, category=PicCategory.STRING, length=x_count)

    if a_count > 0 and n_count == 0 and x_count == 0 and not edited:
        return PicClause(raw=raw, category=PicCategory.ALPHABETIC, length=a_count)

    if n_count > 0 and x_count == 0 and a_count == 0 and not edited:
        cat = PicCategory.SIGNED_NUMERIC if signed else PicCategory.NUMERIC
        return PicClause(raw=raw, category=cat, length=n_count)

    # Mixed or insertion-edited picture.
    # Presence of X or A means alphanumeric-edited; pure 9s with edit chars → numeric-edited.
    tokens = _tokenize_edited(body)
    total = sum(count for _, count in tokens) or None
    edit_symbols = [sym for sym, _ in tokens if sym in _EDIT_SYMBOL_CHARS or sym in ("CR", "DB")]
    edit_symbols = list(dict.fromkeys(edit_symbols)) or None
    cat = PicCategory.ALPHANUMERIC_EDITED if (x_count > 0 or a_count > 0) else PicCategory.NUMERIC_EDITED
    return PicClause(raw=raw, category=cat, length=total, edit_symbols=edit_symbols)
