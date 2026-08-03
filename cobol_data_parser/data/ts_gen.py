"""TypeScript interface generation from a parsed DataItem tree.

Generates one `interface` per top-level (01/77) record, targeting the shape
of decode_record()'s decoded values (see schema_common.py) rather than
emit()'s JSON metadata shape.
"""
from __future__ import annotations

from .models import DataItem
from .schema_common import ValueField, ValueKind, build_value_fields, pascal_case


def _scalar_ts_type(f: ValueField) -> str:
    if f.value_kind == ValueKind.STRING:
        return "string"
    if f.value_kind == ValueKind.INTEGER:
        return "number"
    if f.value_kind == ValueKind.DECIMAL:
        # decimal-as-string to avoid floating-point precision loss (JS has
        # no arbitrary-precision decimal type) — same rationale as the
        # OpenAPI generator.
        return "string"
    if f.value_kind == ValueKind.FLOAT:
        return "number"
    raise AssertionError(f"unclassified value_kind for field {f.name!r}")


def _field_comment(f: ValueField) -> str | None:
    if f.value_kind == ValueKind.DECIMAL:
        return "decimal — represented as a string to avoid floating-point precision loss"
    return None


def _render_type(f: ValueField, indent: str) -> str:
    base = _render_object(f.children, indent + "  ") if f.is_group else _scalar_ts_type(f)
    return f"Array<{base}>" if f.occurs is not None else base


def _render_object(fields: list[ValueField], indent: str) -> str:
    lines = ["{"]
    for f in fields:
        type_str = _render_type(f, indent)
        comment = _field_comment(f)
        suffix = f"  // {comment}" if comment else ""
        lines.append(f'{indent}"{f.name}": {type_str};{suffix}')
    lines.append(indent[:-2] + "}")
    return "\n".join(lines)


def to_typescript(items: list[DataItem]) -> str:
    """Generate TypeScript `interface` declarations mirroring
    decode_record()'s decoded-value shape — one interface per top-level
    01/77 record with children.

    Field keys keep their original COBOL names as quoted string-literal
    keys (e.g. "CUST-ID") rather than being camelCased, staying lossless
    and consistent with emit()'s JSON output keys; only the top-level
    interface name is PascalCased, since TS identifiers can't contain '-'.

    DECIMAL fields (fields with a fractional part) are typed `string`, not
    `number`, to avoid floating-point precision loss. REDEFINES aliases and
    single-target RENAMES appear as separate sibling properties, matching
    decode_record() (see schema_common.py's build_value_fields()). FILLER
    and level-88 items are excluded, matching emit().
    """
    blocks: list[str] = []
    for item in items:
        if not item.is_group:
            continue
        fields = build_value_fields(item.children)
        body = _render_object(fields, "  ")
        blocks.append(f"export interface {pascal_case(item.name)} {body}")
    return "\n\n".join(blocks)
