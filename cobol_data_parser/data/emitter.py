from __future__ import annotations

import json

from .models import DataItem, OccursClause


def _occurs_value(oc: OccursClause) -> int | dict:
    """Convert OccursClause to a JSON-serialisable scalar or object."""
    if oc.is_variable:
        return {"min": oc.min_occurs, "max": oc.max_occurs, "depending_on": oc.depending_on}
    if oc.min_occurs != oc.max_occurs:
        return {"min": oc.min_occurs, "max": oc.max_occurs}
    return oc.max_occurs  # Simple fixed OCCURS → plain int


def _emit_elementary(item: DataItem) -> dict:
    """Emit an elementary (non-group) item node — type/length/precision/scale/usage."""
    node: dict = {}
    if item.pic:
        node["type"] = item.pic.category.value
        if item.pic.length is not None:
            node["length"] = item.pic.length
        if item.pic.precision is not None:
            node["precision"] = item.pic.precision
        if item.pic.scale is not None:
            node["scale"] = item.pic.scale
    if item.offset is not None:
        node["offset"] = item.offset
    if item.byte_length is not None:
        node["bytes"] = item.byte_length
    if item.usage and item.usage != "DISPLAY":
        node["usage"] = item.usage
    if item.sign_separate:
        node["sign"] = "leading-separate" if item.sign_leading else "trailing-separate"
    if item.renames:
        node["renames"] = [item.renames, item.renames_thru] if item.renames_thru else item.renames
    return node


def _emit_group_children(children: list[DataItem]) -> dict:
    """Emit group children, folding REDEFINES aliases into the base field's 'union' array."""
    base_items: list[DataItem] = []
    aliases_by_target: dict[str, list[DataItem]] = {}

    for child in children:
        if child.is_filler or child.level == 88:
            continue
        if child.redefines:
            aliases_by_target.setdefault(child.redefines, []).append(child)
        else:
            base_items.append(child)

    result: dict = {}
    base_names = {item.name for item in base_items}

    for item in base_items:
        node = _emit_item_body(item)
        aliases = aliases_by_target.get(item.name, [])
        if aliases:
            node["union"] = [_emit_union_member(alias) for alias in aliases]
        result[item.name] = node

    # Aliases whose target is not a sibling — emit as-is (orphaned REDEFINES)
    for target, aliases in aliases_by_target.items():
        if target not in base_names:
            for alias in aliases:
                result[alias.name] = _emit_item_body(alias)

    return result


def _emit_union_member(item: DataItem) -> dict:
    """Emit a REDEFINES alias as a union member with an explicit 'name' key."""
    node: dict = {"name": item.name}
    if item.is_group:
        fields = _emit_group_children(item.children)
        if item.offset is not None:
            node["offset"] = item.offset
        if item.byte_length is not None:
            node["bytes"] = item.byte_length
        if item.occurs is not None:
            node["occurs"] = _occurs_value(item.occurs)
        node["fields"] = fields
    else:
        node.update(_emit_elementary(item))
        if item.occurs is not None:
            node["occurs"] = _occurs_value(item.occurs)
    return node


def _emit_item_body(item: DataItem) -> dict:
    """Emit the body of a DataItem (without a 'name' key)."""
    if item.is_group:
        fields = _emit_group_children(item.children)
        if item.occurs is not None:
            node: dict = {}
            if item.offset is not None:
                node["offset"] = item.offset
            if item.byte_length is not None:
                node["bytes"] = item.byte_length
            node["occurs"] = _occurs_value(item.occurs)
            node["fields"] = fields
            return node
        return fields
    else:
        node = _emit_elementary(item)
        if item.occurs is not None:
            node["occurs"] = _occurs_value(item.occurs)
        return node


def emit(items: list[DataItem]) -> dict:
    """Convert a list of top-level DataItems to a JSON-serialisable dict.

    REDEFINES aliases are folded into their base field's 'union' array rather
    than appearing as top-level siblings.
    """
    base_items: list[DataItem] = []
    aliases_by_target: dict[str, list[DataItem]] = {}

    for item in items:
        if item.is_filler:
            continue
        if item.redefines:
            aliases_by_target.setdefault(item.redefines, []).append(item)
        else:
            base_items.append(item)

    base_names = {item.name for item in base_items}
    result: dict = {}

    for item in base_items:
        node = _emit_item_body(item)
        aliases = aliases_by_target.get(item.name, [])
        if aliases:
            node["union"] = [_emit_union_member(alias) for alias in aliases]
        result[item.name] = node

    for target, aliases in aliases_by_target.items():
        if target not in base_names:
            for alias in aliases:
                result[alias.name] = _emit_item_body(alias)

    return result


def to_json(items: list[DataItem], indent: int = 2) -> str:
    return json.dumps(emit(items), indent=indent, ensure_ascii=False)
