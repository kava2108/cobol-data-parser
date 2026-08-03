"""Human-readable data-item definition document generation (Markdown table).

Renders the same parsed/offset-assigned DataItem tree used by emitter.py,
but as a flat, hierarchy-indented table — the "データ項目定義書" format
commonly used to hand off a copybook's physical layout for review.
"""
from __future__ import annotations

from .models import DataItem, OccursClause, PicCategory

_HEADER = ["Level", "項目名", "PIC", "USAGE", "桁数", "バイト数", "オフセット", "REDEFINES", "OCCURS"]

_TEXT_CATEGORIES = (
    PicCategory.STRING,
    PicCategory.ALPHABETIC,
    PicCategory.ALPHANUMERIC_EDITED,
    PicCategory.NUMERIC_EDITED,
)


def _digits_cell(item: DataItem) -> str:
    pic = item.pic
    if pic is None or pic.category in _TEXT_CATEGORIES:
        return ""
    if pic.scale is not None:
        return f"{pic.precision or 0},{pic.scale}"
    if pic.length is not None:
        return str(pic.length)
    return ""


def _occurs_cell(oc: OccursClause | None) -> str:
    if oc is None:
        return ""
    if oc.is_variable:
        return f"{oc.min_occurs}〜{oc.max_occurs} ({oc.depending_on})"
    if oc.min_occurs != oc.max_occurs:
        return f"{oc.min_occurs}〜{oc.max_occurs}"
    return str(oc.max_occurs)


def _name_cell(item: DataItem) -> str:
    if not item.renames:
        return item.name
    target = f"{item.renames} THRU {item.renames_thru}" if item.renames_thru else item.renames
    return f"{item.name}（RENAMES {target}）"


def _row(item: DataItem, depth: int) -> list[str]:
    indent = "　　" * depth
    return [
        f"{indent}{item.level:02d}",
        _name_cell(item),
        item.pic.raw if item.pic else "",
        item.usage if (item.usage and item.usage != "DISPLAY") else "",
        _digits_cell(item),
        "" if item.byte_length is None else str(item.byte_length),
        "" if item.offset is None else str(item.offset),
        item.redefines or "",
        _occurs_cell(item.occurs),
    ]


def _walk(item: DataItem, depth: int, rows: list[list[str]]) -> None:
    rows.append(_row(item, depth))
    for child in item.children:
        _walk(child, depth + 1, rows)


def to_markdown_table(items: list[DataItem]) -> str:
    """Render a parsed DataItem tree as a Markdown data-item definition table.

    Every item — including FILLER, level 66 (RENAMES), and level 88
    (condition names) — is listed, since a layout definition document is
    meant to account for every byte, not just the fields an API consumer
    would want (see emitter.py for that filtered view).
    """
    rows: list[list[str]] = []
    for root in items:
        _walk(root, 0, rows)

    lines = [
        "| " + " | ".join(_HEADER) + " |",
        "|" + "|".join(["---"] * len(_HEADER)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
    return "\n".join(lines)
