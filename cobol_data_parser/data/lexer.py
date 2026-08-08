from __future__ import annotations

import re

_PIC_TOKEN_RE = re.compile(
    r"((?<![A-Z0-9-])(?:PIC|PICTURE)(?![A-Z0-9-])"
    r"(?:\s+(?<![A-Z0-9-])IS(?![A-Z0-9-]))?\s+)(\S+)",
    re.IGNORECASE,
)
_PERIOD_PLACEHOLDER = "\x00"


def _mask_pic_periods(text: str) -> str:
    """Replace a PICTURE clause's own embedded periods (explicit decimal-point
    editing, e.g. `PIC ZZZ,ZZ9.99`) with a placeholder before splitting on
    periods. Without this, that internal period is indistinguishable from the
    entry's terminating period and the clause is truncated (`ZZZ,ZZ9.99.` ->
    `ZZZ,ZZ9`, dropping everything from the decimal point onward)."""
    def repl(m: re.Match) -> str:
        keyword, token = m.group(1), m.group(2)
        if token.endswith("."):
            return keyword + token[:-1].replace(".", _PERIOD_PLACEHOLDER) + "."
        return keyword + token.replace(".", _PERIOD_PLACEHOLDER)

    return _PIC_TOKEN_RE.sub(repl, text)


def split_data_items(logical_lines: list[str]) -> list[str]:
    """Split joined logical source into individual data item declaration strings."""
    full_text = _mask_pic_periods(" ".join(logical_lines))
    raw_entries = re.split(r"\.\s*", full_text)

    entries = []
    for entry in raw_entries:
        entry = re.sub(r"\s+", " ", entry).strip().replace(_PERIOD_PLACEHOLDER, ".")
        if not entry:
            continue
        # Skip section/division headers and FD/SD file descriptors
        if re.match(
            r"^(DATA\s+DIVISION|WORKING-STORAGE\s+SECTION|FILE\s+SECTION|"
            r"LOCAL-STORAGE\s+SECTION|LINKAGE\s+SECTION|COMMUNICATION\s+SECTION|"
            r"REPORT\s+SECTION|PROCEDURE\s+DIVISION|IDENTIFICATION\s+DIVISION|"
            r"ENVIRONMENT\s+DIVISION|FD\s|SD\s)",
            entry,
            re.IGNORECASE,
        ):
            continue
        # Keep data items (level number) and COPY statements (for later expansion)
        if not re.match(r"^\d{1,2}\s+\S", entry) and not re.match(
            r"^COPY\s+\S", entry, re.IGNORECASE
        ):
            continue
        entries.append(entry)

    return entries
