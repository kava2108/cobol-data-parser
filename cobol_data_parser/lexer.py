from __future__ import annotations

import re


def _detect_fixed_format(lines: list[str]) -> bool:
    """Detect fixed format by checking for 6-digit sequence numbers in column 1-6."""
    for line in lines:
        # True fixed format has numeric sequence numbers in the first 6 columns
        if len(line) >= 6 and line[:6].isdigit():
            return True
    return False


def preprocess(text: str, fixed_format: bool | None = None) -> list[str]:
    """Return logical source lines with comments removed and continuations joined."""
    raw_lines = text.splitlines()

    if fixed_format is None:
        fixed_format = _detect_fixed_format(raw_lines)

    logical: list[str] = []

    for raw in raw_lines:
        if fixed_format:
            line = raw.ljust(7)
            indicator = line[6]
            code = line[7:72].rstrip() if len(line) > 7 else ""

            if indicator in ("*", "/"):
                continue
            if indicator == "-":
                if logical:
                    cont = code.lstrip()
                    # Strip leading quote in string continuations
                    if cont and cont[0] in ('"', "'"):
                        cont = cont[1:]
                    logical[-1] += " " + cont
                continue
            logical.append(code)
        else:
            stripped = raw.strip()
            if stripped.startswith("*>") or stripped.startswith("* ") or stripped == "*":
                continue
            logical.append(stripped)

    return logical


def split_data_items(logical_lines: list[str]) -> list[str]:
    """Split joined logical source into individual data item declaration strings."""
    full_text = " ".join(logical_lines)
    raw_entries = re.split(r"\.\s*", full_text)

    entries = []
    for entry in raw_entries:
        entry = re.sub(r"\s+", " ", entry).strip()
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
