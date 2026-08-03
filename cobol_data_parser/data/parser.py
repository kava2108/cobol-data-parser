from __future__ import annotations

from pathlib import Path

from ..common.lexer import preprocess
from .layout import assign_offsets, resolve_renames
from .lexer import split_data_items
from .models import DataItem, OccursClause, PicCategory, PicClause
from .pic_parser import parse_pic
from .storage import compute_byte_length

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


def _parse_renames_entry(name: str, tokens: list[str]) -> DataItem:
    """66 <name> RENAMES <target> [THRU|THROUGH <target2>]."""
    renames: str | None = None
    renames_thru: str | None = None
    if len(tokens) >= 4 and tokens[2].upper() == "RENAMES":
        renames = tokens[3].upper()
        if len(tokens) >= 6 and tokens[4].upper() in ("THRU", "THROUGH"):
            renames_thru = tokens[5].upper()
    return DataItem(level=66, name=name, renames=renames, renames_thru=renames_thru)


def _parse_entry(entry: str) -> DataItem | None:
    tokens = entry.split()
    if len(tokens) < 2:
        return None
    try:
        level = int(tokens[0])
    except ValueError:
        return None

    name = tokens[1].upper()

    if level == 66:
        return _parse_renames_entry(name, tokens)
    pic: PicClause | None = None
    usage: str | None = None
    redefines: str | None = None
    occurs: OccursClause | None = None
    sign_separate = False
    sign_leading = False

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

        elif t == "SIGN":
            # SIGN IS [LEADING|TRAILING] [SEPARATE [CHARACTER]]
            j = i + 1
            if j < len(tokens) and tokens[j].upper() == "IS":
                j += 1
            if j < len(tokens) and tokens[j].upper() in ("LEADING", "TRAILING"):
                sign_leading = tokens[j].upper() == "LEADING"
                i = j
                j += 1
            if j < len(tokens) and tokens[j].upper() == "SEPARATE":
                sign_separate = True
                i = j
                j += 1
                if j < len(tokens) and tokens[j].upper() == "CHARACTER":
                    i = j

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
        byte_length=compute_byte_length(pic, usage, sign_separate=sign_separate),
        sign_separate=sign_separate,
        sign_leading=sign_leading,
    )


def _build_tree(flat: list[DataItem]) -> list[DataItem]:
    roots: list[DataItem] = []
    stack: list[tuple[int, DataItem]] = []
    last_real_level = 0

    for item in flat:
        if item.level in (1, 77):
            roots.append(item)
            stack = [(item.level, item)]
            last_real_level = item.level
            continue

        # Level 66 (RENAMES) is a sibling of the fields it renames, not a
        # child of whichever elementary item happens to precede it — unlike
        # level 88 (condition names), whose large level number conveniently
        # keeps it attached to the immediately preceding item via the normal
        # pop rule below. Pop as if it shared its last real sibling's level.
        pop_level = last_real_level if item.level == 66 else item.level

        while stack and stack[-1][0] >= pop_level:
            stack.pop()

        if stack:
            stack[-1][1].children.append(item)
        else:
            roots.append(item)

        if item.level != 66:
            stack.append((item.level, item))
        if item.level not in (66, 88):
            last_real_level = item.level

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
        from ..common.copybook import expand_copies
        dirs = [Path(d) for d in copybook_dirs]
        entries = expand_copies(entries, dirs, split_data_items, fixed_format)

    flat: list[DataItem] = []
    for entry in entries:
        item = _parse_entry(entry)
        if item is not None:
            flat.append(item)

    roots = _build_tree(flat)
    assign_offsets(roots)
    resolve_renames(roots)
    return roots
