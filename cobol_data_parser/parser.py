from __future__ import annotations

from pathlib import Path

from .lexer import preprocess, split_data_items
from .models import DataItem, OccursClause, PicCategory, PicClause
from .pic_parser import parse_pic

_USAGE_MAP: dict[str, str] = {
    "COMP": "COMP",
    "COMPUTATIONAL": "COMP",
    "COMP-1": "COMP-1",
    "COMPUTATIONAL-1": "COMP-1",
    "COMP-2": "COMP-2",
    "COMPUTATIONAL-2": "COMP-2",
    "COMP-3": "COMP-3",
    "COMPUTATIONAL-3": "COMP-3",
    "COMP-4": "COMP-4",
    "COMPUTATIONAL-4": "COMP-4",
    "COMP-5": "COMP-5",
    "COMPUTATIONAL-5": "COMP-5",
    "BINARY": "BINARY",
    "PACKED-DECIMAL": "PACKED-DECIMAL",
    "DISPLAY": "DISPLAY",
    "INDEX": "INDEX",
    "POINTER": "POINTER",
}

_USAGE_CATEGORY: dict[str, PicCategory] = {
    "COMP": PicCategory.BINARY,
    "COMP-4": PicCategory.BINARY,
    "BINARY": PicCategory.BINARY,
    "COMP-5": PicCategory.BINARY,
    "COMP-3": PicCategory.PACKED_DECIMAL,
    "PACKED-DECIMAL": PicCategory.PACKED_DECIMAL,
}


def _parse_occurs(tokens: list[str], start: int) -> tuple[OccursClause | None, int]:
    """Parse an OCCURS clause starting at tokens[start] (the token after 'OCCURS').

    Returns (OccursClause, index-of-last-consumed-token).
    """
    i = start
    if i >= len(tokens):
        return None, i

    try:
        min_count = int(tokens[i])
    except ValueError:
        return None, i

    max_count = min_count
    depending_on: str | None = None

    while i + 1 < len(tokens):
        nxt = tokens[i + 1].upper()
        if nxt == "TO":
            i += 2
            if i < len(tokens):
                try:
                    max_count = int(tokens[i])
                except ValueError:
                    pass
        elif nxt == "TIMES":
            i += 1
        elif nxt == "DEPENDING":
            i += 1
            if i + 1 < len(tokens) and tokens[i + 1].upper() == "ON":
                i += 2
                if i < len(tokens):
                    depending_on = tokens[i].upper()
            break
        else:
            break

    oc = OccursClause(min_occurs=min_count, max_occurs=max_count, depending_on=depending_on)
    return oc, i


def _parse_entry(entry: str) -> DataItem | None:
    tokens = entry.split()
    if len(tokens) < 2:
        return None
    try:
        level = int(tokens[0])
    except ValueError:
        return None

    name = tokens[1].upper()
    pic: PicClause | None = None
    usage: str | None = None
    redefines: str | None = None
    occurs: OccursClause | None = None

    i = 2
    while i < len(tokens):
        t = tokens[i].upper()

        if t in ("PIC", "PICTURE"):
            i += 1
            if i < len(tokens) and tokens[i].upper() == "IS":
                i += 1
            if i < len(tokens):
                pic = parse_pic(tokens[i])

        elif t == "REDEFINES":
            i += 1
            if i < len(tokens):
                redefines = tokens[i].upper()

        elif t == "OCCURS":
            occurs, i = _parse_occurs(tokens, i + 1)

        elif t == "USAGE":
            i += 1
            if i < len(tokens) and tokens[i].upper() == "IS":
                i += 1
            if i < len(tokens):
                usage = _USAGE_MAP.get(tokens[i].upper())

        elif t in _USAGE_MAP:
            usage = _USAGE_MAP[t]

        elif t == "VALUE":
            break  # VALUE clause can be complex; skip the rest

        i += 1

    if pic and usage and usage in _USAGE_CATEGORY:
        pic = PicClause(
            raw=pic.raw,
            category=_USAGE_CATEGORY[usage],
            length=pic.length,
            precision=pic.precision,
            scale=pic.scale,
        )

    return DataItem(
        level=level,
        name=name,
        pic=pic,
        usage=usage,
        redefines=redefines,
        occurs=occurs,
    )


def _build_tree(flat: list[DataItem]) -> list[DataItem]:
    roots: list[DataItem] = []
    stack: list[tuple[int, DataItem]] = []

    for item in flat:
        if item.level in (1, 77):
            roots.append(item)
            stack = [(item.level, item)]
            continue

        while stack and stack[-1][0] >= item.level:
            stack.pop()

        if stack:
            stack[-1][1].children.append(item)
        else:
            roots.append(item)

        stack.append((item.level, item))

    return roots


def parse(
    text: str,
    fixed_format: bool | None = None,
    copybook_dirs: list[str | Path] | None = None,
) -> list[DataItem]:
    """Parse COBOL DATA DIVISION text and return top-level DataItems.

    Args:
        text: Raw COBOL source text (DATA DIVISION or full program).
        fixed_format: True = fixed (cols 1-72), False = free, None = auto-detect.
        copybook_dirs: Directories to search when expanding COPY statements.
    """
    logical = preprocess(text, fixed_format=fixed_format)
    entries = split_data_items(logical)

    if copybook_dirs:
        from .copybook import expand_copies
        dirs = [Path(d) for d in copybook_dirs]
        entries = expand_copies(entries, dirs, fixed_format)

    flat: list[DataItem] = []
    for entry in entries:
        item = _parse_entry(entry)
        if item is not None:
            flat.append(item)

    return _build_tree(flat)
