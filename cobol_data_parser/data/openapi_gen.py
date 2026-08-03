"""OpenAPI (JSON Schema) component generation from a parsed DataItem tree.

Generates one `components/schemas` entry per top-level (01/77) record,
targeting the shape of decode_record()'s decoded values (see
schema_common.py) rather than emit()'s JSON metadata shape.
"""
from __future__ import annotations

import json

from .models import DataItem
from .schema_common import ValueField, ValueKind, build_value_fields, pascal_case


def _scalar_schema(f: ValueField) -> dict:
    if f.value_kind == ValueKind.STRING:
        schema: dict = {"type": "string"}
        max_length = f.length or f.byte_length
        if max_length:
            schema["maxLength"] = max_length
        return schema

    if f.value_kind == ValueKind.INTEGER:
        return {"type": "integer"}

    if f.value_kind == ValueKind.DECIMAL:
        # JSON Schema/OpenAPI has no arbitrary-precision decimal type;
        # `type: number` risks float precision loss, so decimals are
        # represented as strings — same convention as the TS generator.
        return {
            "type": "string",
            "description": "Decimal value, represented as a string to avoid floating-point precision loss.",
        }

    if f.value_kind == ValueKind.FLOAT:
        return {"type": "number"}

    raise AssertionError(f"unclassified value_kind for property {f.name!r}")


def _field_schema(f: ValueField) -> dict:
    schema = _object_schema(f.children) if f.is_group else _scalar_schema(f)
    if f.occurs is None:
        return schema
    return {
        "type": "array",
        "items": schema,
        "minItems": f.occurs.min_occurs,
        "maxItems": f.occurs.max_occurs,
    }


def _object_schema(fields: list[ValueField]) -> dict:
    return {
        "type": "object",
        "properties": {f.name: _field_schema(f) for f in fields},
        "required": [f.name for f in fields],
    }


def to_openapi_schema(items: list[DataItem]) -> dict:
    """Generate an OpenAPI `components/schemas` dict mirroring
    decode_record()'s decoded-value shape — one schema per top-level 01/77
    record with children.

    Property keys keep their original COBOL names (JSON Schema allows
    arbitrary string keys, so no renaming is needed); only the schema name
    itself is PascalCased for readability. DECIMAL fields (a fractional
    part present) are typed `string` with a descriptive note, not `number`,
    to avoid floating-point precision loss. REDEFINES aliases and
    single-target RENAMES appear as separate sibling properties, matching
    decode_record() (see schema_common.py's build_value_fields()). FILLER
    and level-88 items are excluded, matching emit().
    """
    schemas = {}
    for item in items:
        if not item.is_group:
            continue
        fields = build_value_fields(item.children)
        schemas[pascal_case(item.name)] = _object_schema(fields)
    return {"components": {"schemas": schemas}}


def to_openapi_json(items: list[DataItem], indent: int = 2) -> str:
    return json.dumps(to_openapi_schema(items), indent=indent, ensure_ascii=False)
