"""Shared value-shape model for the SQL/TypeScript/OpenAPI generators.

sql_gen.py / ts_gen.py / openapi_gen.py all target the shape of *decoded*
values — what decode_record() actually returns — rather than the JSON
metadata shape emit() produces. The two differ for REDEFINES: emit() folds
aliases into a "union" array, but decode_record() decodes the base field
and every alias independently and returns them as sibling keys (see
codec.py). Likewise, only single-target RENAMES (level 66, no THRU) appear
in decode_record()'s output; THRU-range RENAMES don't. build_value_fields()
mirrors that sibling shape so all three generators stay consistent with the
rest of the tool and with each other.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .layout import group_slots
from .models import DataItem, OccursClause, PicCategory

_TEXT_CATEGORIES = (
    PicCategory.STRING,
    PicCategory.ALPHABETIC,
    PicCategory.ALPHANUMERIC_EDITED,
    PicCategory.NUMERIC_EDITED,
)
_PACKED_USAGES = {"COMP-3", "PACKED-DECIMAL"}
_BINARY_USAGES = {"COMP", "COMP-4", "COMP-5", "BINARY"}
_FLOAT_USAGES = {"COMP-1", "COMP-2"}


class ValueKind(str, Enum):
    """The Python type decode_record() returns for an elementary item."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    FLOAT = "float"


def classify_value_kind(item: DataItem) -> ValueKind:
    """Classify decode_record()'s return type for an elementary item.

    Mirrors codec.py's _decode_scalar dispatch order exactly (text
    category first, then FLOAT usage, then PACKED/BINARY by usage-or-
    category, then the zoned-decimal fallback) so the two never diverge.

    A PACKED_DECIMAL/zoned-numeric field only decodes to Decimal when its
    PIC has a fractional part (scale > 0, e.g. PIC 9(5)V99 COMP-3) — a plain
    PIC 9(5) COMP-3 (no V) decodes to a plain int (see codec.py's
    _apply_scale). BINARY usages always decode to int regardless of any PIC
    scale — the codec never applies scale to binary integers.
    """
    pic = item.pic
    category = pic.category if pic else None

    if category in _TEXT_CATEGORIES:
        return ValueKind.STRING
    if item.usage in _FLOAT_USAGES:
        return ValueKind.FLOAT

    scale = (pic.scale or 0) if pic else 0
    if item.usage in _PACKED_USAGES or category == PicCategory.PACKED_DECIMAL:
        return ValueKind.DECIMAL if scale > 0 else ValueKind.INTEGER
    if item.usage in _BINARY_USAGES or category == PicCategory.BINARY:
        return ValueKind.INTEGER

    return ValueKind.DECIMAL if scale > 0 else ValueKind.INTEGER


@dataclass
class ValueField:
    """One field in the decoded-value shape. Elementary when `children` is
    empty (`value_kind` set); a group otherwise (`value_kind` is None).
    `occurs` marks array cardinality independently of that — a scalar or a
    group can each be an array.
    """

    name: str
    occurs: Optional[OccursClause]
    value_kind: Optional[ValueKind]
    length: Optional[int]
    precision: Optional[int]
    scale: Optional[int]
    byte_length: Optional[int]
    children: list["ValueField"] = field(default_factory=list)

    @property
    def is_group(self) -> bool:
        return bool(self.children)

    @property
    def digits(self) -> Optional[int]:
        """Total digit count for a numeric field: PIC 9(n) (no V) and
        PACKED-DECIMAL/BINARY overrides store the count in `length`;
        PIC 9(n)V9(m) stores it in `precision`."""
        return self.precision if self.precision is not None else self.length


def _build_field(item: DataItem) -> ValueField:
    if item.is_group:
        return ValueField(
            name=item.name,
            occurs=item.occurs,
            value_kind=None,
            length=None,
            precision=None,
            scale=None,
            byte_length=item.byte_length,
            children=build_value_fields(item.children),
        )
    pic = item.pic
    return ValueField(
        name=item.name,
        occurs=item.occurs,
        value_kind=classify_value_kind(item),
        length=pic.length if pic else None,
        precision=pic.precision if pic else None,
        scale=pic.scale if pic else None,
        byte_length=item.byte_length,
        children=[],
    )


def build_value_fields(children: list[DataItem]) -> list[ValueField]:
    """Flatten one level of DataItem children into decode_record()'s sibling
    shape: REDEFINES aliases as independent siblings (not a union), plus
    single-target RENAMES (level 66, no THRU) as a duplicate sibling.
    FILLER, level-88, and THRU-range RENAMES are excluded — same as
    decode_record()."""
    slots, orphans = group_slots(children)
    fields: list[ValueField] = []

    for base_item, aliases in slots:
        if not base_item.is_filler:
            fields.append(_build_field(base_item))
        for alias in aliases:
            if not alias.is_filler:
                fields.append(_build_field(alias))

    for orphan in orphans:
        if not orphan.is_filler:
            fields.append(_build_field(orphan))

    for child in children:
        if (
            child.level == 66
            and child.renames is not None
            and child.renames_thru is None
            and child.pic is not None
            and child.offset is not None
            and child.byte_length is not None
        ):
            fields.append(_build_field(child))

    return fields


def sql_identifier(name: str) -> str:
    """COBOL names are hyphenated (e.g. CUST-ID); SQL identifiers can't
    contain '-', so replace it with '_'."""
    return name.replace("-", "_")


def pascal_case(name: str) -> str:
    """COBOL-name -> PascalCase, for generating a valid TS/schema type
    identifier from a record name (e.g. CUSTOMER-REC -> CustomerRec)."""
    return "".join(part.capitalize() for part in name.replace("_", "-").split("-") if part)
