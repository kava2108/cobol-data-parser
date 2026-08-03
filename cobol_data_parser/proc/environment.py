"""ENVIRONMENT DIVISION (FILE-CONTROL SELECT) and DATA DIVISION FILE SECTION
(FD) scanning — the file-access analysis counterpart of data/parser.py's
DATA DIVISION item parsing.

Unlike data/lexer.py's split_data_items() (which discards DIVISION/SECTION
headers entirely once it's found the data items it wants), this module needs
to see those headers itself, to know when a FILE SECTION's FD has ended and
the next one (or WORKING-STORAGE/PROCEDURE DIVISION) has begun. So it uses
its own entry-splitting rather than reusing split_data_items().
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..common.lexer import preprocess
from .models import FileDescriptor

_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")


def _mask_quoted(text: str) -> str:
    """Blank out the contents of quoted literals (preserving delimiters and
    length) before splitting on periods. Without this, a literal like
    `ASSIGN TO "CUSTOMER.DAT"` — an idiomatic GnuCOBOL/Micro Focus form —
    would have its internal period mistaken for a statement terminator,
    splitting the SELECT clause in two and losing everything after it
    (ORGANIZATION IS/RECORD KEY IS/...) to a fragment this module no longer
    recognizes as part of the same SELECT."""
    return _QUOTED_RE.sub(lambda m: m.group(0)[0] + "X" * (len(m.group(0)) - 2) + m.group(0)[0], text)


def _split_entries(logical_lines: list[str]) -> list[str]:
    full_text = _mask_quoted(" ".join(logical_lines))
    raw_entries = re.split(r"\.\s*", full_text)
    return [cleaned for e in raw_entries if (cleaned := re.sub(r"\s+", " ", e).strip())]


_SELECT_RE = re.compile(r"^SELECT\s+(?:OPTIONAL\s+)?([A-Z0-9][A-Z0-9-]*)\s+ASSIGN\b", re.IGNORECASE)
_ORGANIZATION_RE = re.compile(r"\bORGANIZATION\s+(?:IS\s+)?(?:LINE\s+SEQUENTIAL|[A-Z]+)", re.IGNORECASE)
_ACCESS_MODE_RE = re.compile(r"\bACCESS\s+MODE\s+IS\s+([A-Z]+)", re.IGNORECASE)
_RECORD_KEY_RE = re.compile(r"\bRECORD\s+KEY\s+IS\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_ALT_KEY_RE = re.compile(r"\bALTERNATE\s+RECORD\s+KEY\s+IS\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_FILE_STATUS_RE = re.compile(r"\bFILE\s+STATUS\s+IS\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_FD_RE = re.compile(r"^(?:FD|SD)\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_RECORD_ENTRY_RE = re.compile(r"^(?:01|77)\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_FD_SCOPE_END_RE = re.compile(
    r"^(?:FD|SD|WORKING-STORAGE\s+SECTION|LOCAL-STORAGE\s+SECTION|"
    r"LINKAGE\s+SECTION|PROCEDURE\s+DIVISION)\b",
    re.IGNORECASE,
)


def _organization_value(entry: str) -> Optional[str]:
    m = _ORGANIZATION_RE.search(entry)
    if not m:
        return None
    # ORGANIZATION IS LINE SEQUENTIAL is two words; every other form
    # (INDEXED/SEQUENTIAL/RELATIVE) is one.
    return "LINE SEQUENTIAL" if "LINE" in m.group(0).upper() else m.group(0).split()[-1].upper()


def _parse_select_entry(entry: str, files: dict[str, FileDescriptor], order: list[str]) -> None:
    m = _SELECT_RE.match(entry)
    if not m:
        return
    name = m.group(1).upper()
    fd = files.setdefault(name, FileDescriptor(name=name))
    if name not in order:
        order.append(name)

    org = _organization_value(entry)
    if org:
        fd.organization = org
    access_m = _ACCESS_MODE_RE.search(entry)
    if access_m:
        fd.access_mode = access_m.group(1).upper()
    key_m = _RECORD_KEY_RE.search(entry)
    if key_m:
        fd.record_key = key_m.group(1).upper()
    alt_keys = [k.upper() for k in _ALT_KEY_RE.findall(entry)]
    if alt_keys:
        fd.alternate_record_keys = alt_keys
    status_m = _FILE_STATUS_RE.search(entry)
    if status_m:
        fd.file_status = status_m.group(1).upper()


def parse_file_descriptors(
    text: str,
    fixed_format: Optional[bool] = None,
    copybook_dirs: Optional[list] = None,
) -> list[FileDescriptor]:
    """Scan a COBOL source for FILE-CONTROL SELECT clauses (ENVIRONMENT
    DIVISION) and FD/01 record declarations (DATA DIVISION FILE SECTION),
    merging each SELECT with its matching FD by file-name.

    `copybook_dirs`, if given, expands COPY statements (common inside FILE
    SECTION, for the record layout under an FD) via
    common/copybook.py's expand_copies() — the same call pattern
    data/parser.py uses for DATA DIVISION COPY statements.
    """
    logical = preprocess(text, fixed_format=fixed_format)
    entries = _split_entries(logical)

    if copybook_dirs:
        from ..common.copybook import expand_copies

        dirs = [Path(d) for d in copybook_dirs]
        entries = expand_copies(entries, dirs, _split_entries, fixed_format)

    files: dict[str, FileDescriptor] = {}
    order: list[str] = []
    current_fd: Optional[str] = None

    for entry in entries:
        if _SELECT_RE.match(entry):
            _parse_select_entry(entry, files, order)
            current_fd = None
            continue

        fd_m = _FD_RE.match(entry)
        if fd_m:
            name = fd_m.group(1).upper()
            files.setdefault(name, FileDescriptor(name=name))
            if name not in order:
                order.append(name)
            current_fd = name
            continue

        if _FD_SCOPE_END_RE.match(entry):
            current_fd = None
            continue

        if current_fd is not None:
            rec_m = _RECORD_ENTRY_RE.match(entry)
            if rec_m:
                files[current_fd].record_names.append(rec_m.group(1).upper())

    return [files[name] for name in order]
