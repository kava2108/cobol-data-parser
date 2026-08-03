"""AST normalization: assign byte offsets across the parsed DataItem tree.

Runs after parsing/type-lowering (byte_length is already known per field —
see storage.py). Each 01/77-level item is treated as its own record and
starts at offset 0. REDEFINES aliases share their target's offset rather
than advancing the cursor. A variable-length field (OCCURS ... DEPENDING ON,
or any unresolved length) makes every offset after it in the same group
unknowable statically, so those are left as None.
"""
from __future__ import annotations

from typing import Optional

from .models import DataItem


def _total_length(item: DataItem) -> Optional[int]:
    """Full storage span of item for one pass through its parent, including
    its own OCCURS multiplication. None if variable or otherwise unknown."""
    unit = item.byte_length
    if unit is None:
        return None
    if item.occurs is None:
        return unit
    if item.occurs.max_occurs != item.occurs.min_occurs:
        return None
    return unit * item.occurs.max_occurs


def _assign_recursive(item: DataItem, offset: Optional[int]) -> None:
    item.offset = offset
    if item.is_group:
        end = _assign_group(item.children, offset)
        item.byte_length = None if offset is None or end is None else end - offset


def group_slots(
    children: list[DataItem],
) -> tuple[list[tuple[DataItem, list[DataItem]]], list[DataItem]]:
    """Group a level's real (non-66/88) children into (base_item, aliases) slots,
    in source order, plus any orphaned REDEFINES whose target isn't a sibling.

    Shared by offset assignment and decoding: both need to know which items
    share the same storage (REDEFINES) versus which advance the cursor.
    """
    real_children = [c for c in children if c.level not in (66, 88)]

    slots: list[tuple[DataItem, list[DataItem]]] = []
    slot_by_name: dict[str, tuple[DataItem, list[DataItem]]] = {}
    orphans: list[DataItem] = []

    for child in real_children:
        if child.redefines:
            target = slot_by_name.get(child.redefines)
            if target is not None:
                target[1].append(child)
            else:
                orphans.append(child)  # target not a (yet-seen) sibling
        else:
            slot = (child, [])
            slots.append(slot)
            slot_by_name[child.name] = slot

    return slots, orphans


def _assign_group(children: list[DataItem], base: Optional[int]) -> Optional[int]:
    """Assign offsets to a group's children sequentially from base.

    REDEFINES aliases are grouped with the sibling they redefine ('slots');
    each slot advances the cursor once, by the largest span among the base
    field and its aliases (an alias may be wider than the field it covers).
    """
    slots, orphans = group_slots(children)

    cursor = base
    for base_item, aliases in slots:
        _assign_recursive(base_item, cursor)
        for alias in aliases:
            _assign_recursive(alias, cursor)

        spans = [_total_length(base_item)] + [_total_length(a) for a in aliases]
        cursor = None if cursor is None or any(s is None for s in spans) else cursor + max(spans)

    for alias in orphans:
        _assign_recursive(alias, cursor)
        span = _total_length(alias)
        cursor = None if cursor is None or span is None else cursor + span

    return cursor


def assign_offsets(items: list[DataItem]) -> None:
    """Compute byte offsets for every field in place.

    Each top-level (01/77-level) item is its own record and starts at offset 0.
    """
    for root in items:
        _assign_recursive(root, 0)


def _resolve_renames_in_group(children: list[DataItem]) -> None:
    real_children = [c for c in children if c.level not in (66, 88)]
    by_name = {c.name: c for c in real_children}

    for child in children:
        if child.level != 66 or child.renames is None:
            continue
        start = by_name.get(child.renames)
        if start is None:
            continue

        child.offset = start.offset

        if child.renames_thru is None:
            child.pic = start.pic
            child.byte_length = start.byte_length
            continue

        end = by_name.get(child.renames_thru)
        if end is None:
            child.byte_length = start.byte_length
            continue

        i0, i1 = real_children.index(start), real_children.index(end)
        if i0 > i1:
            i0, i1 = i1, i0
        spans = [c.byte_length for c in real_children[i0 : i1 + 1]]
        child.byte_length = None if any(s is None for s in spans) else sum(spans)


def resolve_renames(items: list[DataItem]) -> None:
    """Resolve level-66 RENAMES items against their target sibling(s).

    Must run after assign_offsets(), since a RENAMES item borrows the offset
    (and, for a single target, the PIC) of the field(s) it renames. RENAMES
    THRU spans get a combined byte_length but no PIC — the range covers
    heterogeneous storage with no single elementary type.
    """
    for item in items:
        _resolve_renames_in_group(item.children)
        resolve_renames(item.children)
