"""Codec layer: decode real record bytes into Python values using a parsed,
offset-assigned DataItem tree (see parser.py / layout.py).

Covers the common mainframe wire formats: EBCDIC text, zoned decimal
(DISPLAY numeric), packed decimal (COMP-3), and binary integers
(COMP/COMP-4/COMP-5/BINARY). IBM hex/IEEE floating point (COMP-1/COMP-2)
and INDEX/POINTER are not decoded — those raise NotImplementedError.

Unlike the static offsets from layout.py (which go to None once an OCCURS
DEPENDING ON field is hit, since its true length isn't known until you have
data), decoding resolves those counts against already-decoded sibling
values and keeps walking with real offsets for the rest of the record.
"""
from __future__ import annotations

import struct
from decimal import Decimal
from typing import Any, Iterator, Optional

from .layout import group_slots
from .models import DataItem, PicCategory

_TEXT_CATEGORIES = (
    PicCategory.STRING,
    PicCategory.ALPHABETIC,
    PicCategory.ALPHANUMERIC_EDITED,
    PicCategory.NUMERIC_EDITED,
)
_PACKED_USAGES = {"COMP-3", "PACKED-DECIMAL"}
_BINARY_USAGES = {"COMP", "COMP-4", "COMP-5", "BINARY"}
_UNSUPPORTED_USAGES = {"COMP-1", "COMP-2", "INDEX", "POINTER"}

_BINARY_STRUCT_CODE = {2: "h", 4: "i", 8: "q"}  # signed; .upper() for unsigned


def _decode_zoned(raw: bytes, signed: bool, scale: int) -> Any:
    """DISPLAY numeric: one EBCDIC/ASCII digit per byte (low nibble = digit).

    A signed field over-punches the sign into the zone (high) nibble of the
    last byte: EBCDIC 0xC/0xF = positive, 0xD/0xB = negative.
    """
    if not raw:
        return 0
    digits = "".join(str(b & 0x0F) for b in raw)
    negative = signed and ((raw[-1] >> 4) & 0x0F) in (0xD, 0xB)
    return _apply_scale(digits, negative, scale)


def _decode_packed(raw: bytes, scale: int) -> Any:
    """COMP-3: two BCD digits per byte, except the final nibble is the sign."""
    nibbles: list[int] = []
    for b in raw:
        nibbles.append((b >> 4) & 0x0F)
        nibbles.append(b & 0x0F)
    sign_nibble = nibbles[-1]
    digits = "".join(str(n) for n in nibbles[:-1])
    negative = sign_nibble in (0xD, 0xB)
    return _apply_scale(digits, negative, scale)


def _apply_scale(digits: str, negative: bool, scale: int) -> Any:
    if scale:
        int_part = digits[: len(digits) - scale] or "0"
        frac_part = digits[len(digits) - scale :]
        value: Any = Decimal(f"{int_part}.{frac_part}")
    else:
        value = int(digits) if digits else 0
    return -value if negative and value else value


def _decode_binary(raw: bytes, signed: bool, byte_order: str) -> int:
    code = _BINARY_STRUCT_CODE.get(len(raw))
    if code is None:
        raise ValueError(f"unsupported binary field width: {len(raw)} bytes")
    if not signed:
        code = code.upper()
    prefix = ">" if byte_order == "big" else "<"
    return struct.unpack(prefix + code, raw)[0]


def _decode_scalar(item: DataItem, raw: bytes, encoding: str, byte_order: str) -> Any:
    usage = item.usage
    if usage in _UNSUPPORTED_USAGES:
        raise NotImplementedError(f"{item.name}: USAGE {usage} decoding is not supported")

    pic = item.pic
    category = pic.category if pic else None

    if category in _TEXT_CATEGORIES:
        return raw.decode(encoding).rstrip(" ")

    scale = (pic.scale or 0) if pic else 0
    # Signedness must come from the raw PIC (S prefix), not category: parser.py
    # overwrites category to BINARY/PACKED-DECIMAL for COMP/COMP-3 usages,
    # which discards whether the original PIC was signed.
    signed = bool(pic) and pic.raw.strip().upper().startswith("S")

    if usage in _PACKED_USAGES or category == PicCategory.PACKED_DECIMAL:
        return _decode_packed(raw, scale)
    if usage in _BINARY_USAGES or category == PicCategory.BINARY:
        return _decode_binary(raw, signed, byte_order)

    return _decode_zoned(raw, signed, scale)


def _element_width(item: DataItem) -> Optional[int]:
    """Width, in bytes, of a single occurrence of item (no OCCURS multiplier)."""
    return item.byte_length


def _decode_element(
    item: DataItem, buffer: bytes, offset: int, encoding: str, byte_order: str
) -> tuple[Any, int]:
    """Decode one occurrence of item (not multiplied by its own OCCURS)."""
    if item.is_group:
        values, end = _decode_group(item, buffer, offset, encoding, byte_order)
        return values, end - offset

    length = _element_width(item)
    if length is None:
        raise ValueError(f"{item.name}: unknown byte length, cannot decode")
    raw = buffer[offset : offset + length]
    return _decode_scalar(item, raw, encoding, byte_order), length


def _resolve_occurs_count(item: DataItem, scope: dict[str, Any]) -> int:
    oc = item.occurs
    assert oc is not None
    if oc.depending_on is None:
        return oc.max_occurs
    if oc.depending_on not in scope:
        raise ValueError(
            f"{item.name}: OCCURS DEPENDING ON {oc.depending_on!r} has not been "
            "decoded yet (it must be a preceding sibling in the same group)"
        )
    return int(scope[oc.depending_on])


def _decode_field(
    item: DataItem, buffer: bytes, offset: int, encoding: str, byte_order: str, scope: dict[str, Any]
) -> tuple[Any, int]:
    """Decode item (handling its own OCCURS, if any). Returns (value, bytes consumed)."""
    if item.occurs is None:
        return _decode_element(item, buffer, offset, encoding, byte_order)

    count = _resolve_occurs_count(item, scope)
    elements: list[Any] = []
    cursor = offset
    for _ in range(count):
        value, used = _decode_element(item, buffer, cursor, encoding, byte_order)
        elements.append(value)
        cursor += used
    return elements, cursor - offset


def _decode_group(
    item: DataItem, buffer: bytes, base_offset: int, encoding: str, byte_order: str
) -> tuple[dict[str, Any], int]:
    slots, orphans = group_slots(item.children)
    values: dict[str, Any] = {}
    cursor = base_offset

    for base_item, aliases in slots:
        value, width = _decode_field(base_item, buffer, cursor, encoding, byte_order, values)
        if not base_item.is_filler:
            values[base_item.name] = value
        for alias in aliases:
            alias_value, alias_width = _decode_field(alias, buffer, cursor, encoding, byte_order, values)
            if not alias.is_filler:
                values[alias.name] = alias_value
            width = max(width, alias_width)
        cursor += width

    for alias in orphans:
        value, width = _decode_field(alias, buffer, cursor, encoding, byte_order, values)
        if not alias.is_filler:
            values[alias.name] = value
        cursor += width

    return values, cursor


def decode_record(
    item: DataItem, buffer: bytes, encoding: str = "cp037", byte_order: str = "big"
) -> dict[str, Any]:
    """Decode one top-level (01/77-level) record's field values from raw bytes.

    REDEFINES aliases are decoded independently and both appear as sibling
    keys (unlike the JSON schema's 'union' folding) — at decode time the
    caller, not this layer, knows which interpretation of the bytes is valid.
    OCCURS DEPENDING ON counts are resolved against already-decoded sibling
    fields, so trailing fields the static AST couldn't offset (see layout.py)
    still decode correctly here.
    """
    offset = item.offset or 0
    if item.is_group:
        values, _end = _decode_group(item, buffer, offset, encoding, byte_order)
        return values
    value, _width = _decode_element(item, buffer, offset, encoding, byte_order)
    return {item.name: value}


def iter_records(
    item: DataItem,
    data: bytes,
    record_length: Optional[int] = None,
    encoding: str = "cp037",
    byte_order: str = "big",
) -> Iterator[dict[str, Any]]:
    """Split a flat byte stream into fixed-length records and decode each one.

    record_length defaults to item.byte_length; pass it explicitly if the
    record's own size is data-dependent (e.g. a top-level OCCURS DEPENDING ON).
    """
    length = record_length if record_length is not None else item.byte_length
    if not length or length <= 0:
        raise ValueError(f"{item.name}: byte_length is unknown/variable; pass record_length explicitly")
    for start in range(0, len(data), length):
        yield decode_record(item, data[start : start + length], encoding, byte_order)
