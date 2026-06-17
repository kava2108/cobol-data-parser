from __future__ import annotations

import json

from .models import DataItem


def _emit_item(item: DataItem) -> dict:
    if item.is_group:
        fields: dict = {}
        for child in item.children:
            if not child.is_filler and child.level not in (66, 88):
                fields[child.name] = _emit_item(child)

        # Wrap in metadata envelope only when OCCURS or REDEFINES is present
        if item.occurs is not None or item.redefines is not None:
            node: dict = {}
            if item.occurs is not None:
                node["occurs"] = item.occurs
            if item.redefines is not None:
                node["redefines"] = item.redefines
            node["fields"] = fields
        else:
            node = fields
    else:
        node = {}
        if item.pic:
            node["type"] = item.pic.category.value
            if item.pic.length is not None:
                node["length"] = item.pic.length
            if item.pic.precision is not None:
                node["precision"] = item.pic.precision
            if item.pic.scale is not None:
                node["scale"] = item.pic.scale
        if item.usage and item.usage != "DISPLAY":
            node["usage"] = item.usage
        if item.occurs is not None:
            node["occurs"] = item.occurs
        if item.redefines is not None:
            node["redefines"] = item.redefines

    return node


def emit(items: list[DataItem]) -> dict:
    """Convert a list of top-level DataItems to a JSON-serializable dict."""
    result = {}
    for item in items:
        if not item.is_filler:
            result[item.name] = _emit_item(item)
    return result


def to_json(items: list[DataItem], indent: int = 2) -> str:
    return json.dumps(emit(items), indent=indent, ensure_ascii=False)
