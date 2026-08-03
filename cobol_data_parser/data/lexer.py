from __future__ import annotations

import re


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
