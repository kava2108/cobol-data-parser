"""COPYBOOK expansion: resolve COPY statements and inline copybook content."""
from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Callable

_COPYBOOK_EXTS = (".cpy", ".CPY", ".cob", ".COB", ".CBL", ".cbl")

# COPY <name> [IN|OF <lib>] [REPLACING ==a== BY ==b== ...]
_COPY_RE = re.compile(
    r"^COPY\s+(\S+?)(?:\s+(?:IN|OF)\s+\S+)?(?:\s+REPLACING\s+(.+))?$",
    re.IGNORECASE,
)

# Pseudo-text pairs: ==old== BY ==new==
_PSEUDO_RE = re.compile(r"==([^=]*)==\s+BY\s+==([^=]*)==", re.IGNORECASE)

# Word pairs: WORD1 BY WORD2  (applied after pseudo-text extraction)
_WORD_RE = re.compile(r"(\S+)\s+BY\s+(\S+)", re.IGNORECASE)


def _load_copybook(name: str, dirs: list[Path]) -> str | None:
    bare = name.rstrip(".")
    for d in dirs:
        for ext in _COPYBOOK_EXTS:
            p = d / (bare + ext)
            if p.exists():
                return p.read_text(encoding="utf-8")
        p = d / bare
        if p.exists():
            return p.read_text(encoding="utf-8")
    return None


def _apply_replacing(content: str, replacing_str: str) -> str:
    """Apply REPLACING clause substitutions to copybook text."""
    remaining = replacing_str
    pseudo_pairs: list[tuple[str, str]] = []

    for m in _PSEUDO_RE.finditer(replacing_str):
        old, new = m.group(1).strip(), m.group(2).strip()
        pseudo_pairs.append((old, new))
        # Blank out matched span so word RE below doesn't re-parse it
        remaining = remaining[: m.start()] + " " * len(m.group(0)) + remaining[m.end() :]

    word_pairs: list[tuple[str, str]] = []
    for m in _WORD_RE.finditer(remaining):
        old = m.group(1)
        if old.upper() not in ("BY", "=="):
            word_pairs.append((old, m.group(2)))

    for old, new in pseudo_pairs:
        if old:
            content = re.sub(re.escape(old), new, content, flags=re.IGNORECASE)

    for old, new in word_pairs:
        content = re.sub(rf"\b{re.escape(old)}\b", new, content, flags=re.IGNORECASE)

    return content


def expand_copies(
    entries: list[str],
    copybook_dirs: list[Path],
    splitter: Callable[[list[str]], list[str]],
    fixed_format: bool | None = None,
    _depth: int = 0,
) -> list[str]:
    """Replace COPY statement entries with the entries from the referenced copybook.

    `splitter` breaks preprocessed copybook source lines back into entries using
    the same convention as `entries` (e.g. DATA DIVISION items or PROCEDURE
    DIVISION statements), so this function stays usable from either division.

    Recursively expands nested COPY statements up to depth 10.
    """
    if _depth > 10:
        return entries

    from .lexer import preprocess

    result: list[str] = []
    for entry in entries:
        m = _COPY_RE.match(entry.strip())
        if not m:
            result.append(entry)
            continue

        book_name = m.group(1).rstrip(".")
        replacing_str = m.group(2)
        content = _load_copybook(book_name, copybook_dirs)

        if content is None:
            warnings.warn(
                f"Copybook not found: {book_name!r} "
                f"(searched in: {[str(d) for d in copybook_dirs]})",
                stacklevel=3,
            )
            result.append(entry)
            continue

        if replacing_str:
            content = _apply_replacing(content, replacing_str)

        copy_entries = splitter(preprocess(content, fixed_format))
        copy_entries = expand_copies(copy_entries, copybook_dirs, splitter, fixed_format, _depth + 1)
        result.extend(copy_entries)

    return result
