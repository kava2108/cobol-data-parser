"""Codec layer: decode real record bytes into Python values, and encode
Python values back into bytes, using a parsed, offset-assigned DataItem
tree (see parser.py / layout.py).

Covers the common mainframe wire formats: EBCDIC text, zoned decimal
(DISPLAY numeric), packed decimal (COMP-3), binary integers
(COMP/COMP-4/COMP-5/BINARY), and IEEE754 floating point (COMP-1 single /
COMP-2 double precision). INDEX/POINTER are not supported — those raise
NotImplementedError.

Unlike the static offsets from layout.py (which go to None once an OCCURS
DEPENDING ON field is hit, since its true length isn't known until you have
data), decoding resolves those counts against already-decoded sibling
values and keeps walking with real offsets for the rest of the record.
encode_record() is decode_record()'s inverse — see its docstring below for
how it handles REDEFINES and OCCURS DEPENDING ON in the write direction.
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
_FLOAT_USAGES = {"COMP-1", "COMP-2"}
_UNSUPPORTED_USAGES = {"INDEX", "POINTER"}

_BINARY_STRUCT_CODE = {2: "h", 4: "i", 8: "q"}  # signed; .upper() for unsigned
_FLOAT_STRUCT_CODE = {4: "f", 8: "d"}  # COMP-1 (4 bytes) / COMP-2 (8 bytes)


def _decode_zoned(
    raw: bytes,
    signed: bool,
    scale: int,
    sign_leading: bool = False,
    sign_separate: bool = False,
    encoding: str = "cp037",
) -> Any:
    """DISPLAY numeric: one EBCDIC/ASCII digit per byte (low nibble = digit).

    A signed field over-punches the sign into the zone (high) nibble of the
    last byte (or first, if SIGN IS LEADING): EBCDIC 0xC/0xF = positive,
    0xD/0xB = negative. SIGN IS ... SEPARATE puts the sign in its own
    '+'/'-' character byte (leading or trailing) instead of over-punching.
    """
    if not raw:
        return 0

    if sign_separate:
        sign_byte, digit_bytes = (raw[:1], raw[1:]) if sign_leading else (raw[-1:], raw[:-1])
        negative = sign_byte.decode(encoding) == "-"
        digits = "".join(str(b & 0x0F) for b in digit_bytes)
        return _apply_scale(digits, negative, scale)

    digits = "".join(str(b & 0x0F) for b in raw)
    sign_byte = raw[0] if sign_leading else raw[-1]
    negative = signed and ((sign_byte >> 4) & 0x0F) in (0xD, 0xB)
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


def _decode_float(raw: bytes, byte_order: str) -> float:
    """COMP-1/COMP-2: IEEE754 single (4 bytes) / double (8 bytes) precision."""
    code = _FLOAT_STRUCT_CODE.get(len(raw))
    if code is None:
        raise ValueError(f"unsupported float field width: {len(raw)} bytes")
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

    if usage in _FLOAT_USAGES:
        return _decode_float(raw, byte_order)

    scale = (pic.scale or 0) if pic else 0
    # Signedness must come from the raw PIC (S prefix), not category: parser.py
    # overwrites category to BINARY/PACKED-DECIMAL for COMP/COMP-3 usages,
    # which discards whether the original PIC was signed.
    signed = bool(pic) and pic.raw.strip().upper().startswith("S")

    if usage in _PACKED_USAGES or category == PicCategory.PACKED_DECIMAL:
        return _decode_packed(raw, scale)
    if usage in _BINARY_USAGES or category == PicCategory.BINARY:
        return _decode_binary(raw, signed, byte_order)

    return _decode_zoned(raw, signed, scale, item.sign_leading, item.sign_separate, encoding)


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


def _decode_renames(children: list[DataItem], buffer: bytes, encoding: str, byte_order: str, values: dict[str, Any]) -> None:
    """Decode level-66 RENAMES items that alias a single target field.

    RENAMES THRU spans combine heterogeneous storage with no single PIC type
    to decode against, so those are left out of the decoded record (they're
    still visible in the JSON schema and layout, just not as decoded values).
    """
    for child in children:
        if child.level != 66 or child.renames is None or child.renames_thru is not None:
            continue
        if child.pic is None or child.offset is None or child.byte_length is None:
            continue
        value, _width = _decode_element(child, buffer, child.offset, encoding, byte_order)
        values[child.name] = value


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

    _decode_renames(item.children, buffer, encoding, byte_order, values)

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


# ─── Encoding: Python values -> raw record bytes (the inverse of decode) ─────


def _encode_text(value: Any, length: int, encoding: str) -> bytes:
    raw = str(value).encode(encoding)
    if len(raw) > length:
        raise ValueError(f"value {value!r} does not fit in {length} bytes")
    pad = " ".encode(encoding)
    return raw + pad * (length - len(raw))


def _encode_zoned(
    value: Any, length: int, signed: bool, scale: int, sign_leading: bool, sign_separate: bool, encoding: str
) -> bytes:
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    negative = dec < 0
    dec = abs(dec)
    scaled = int((dec * (10**scale)).to_integral_value()) if scale else int(dec)

    digit_count = length - 1 if sign_separate else length
    digits = str(scaled).rjust(digit_count, "0")
    if len(digits) > digit_count:
        raise ValueError(f"value {value!r} does not fit in {digit_count} digits")

    if sign_separate:
        sign_char = ("-" if negative else "+").encode(encoding)
        digit_bytes = digits.encode(encoding)
        return sign_char + digit_bytes if sign_leading else digit_bytes + sign_char

    raw = bytearray(digits.encode(encoding))
    if signed and negative:
        idx = 0 if sign_leading else -1
        raw[idx] = (0xD << 4) | (raw[idx] & 0x0F)
    return bytes(raw)


def _encode_packed(value: Any, byte_length: int, scale: int) -> bytes:
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    negative = dec < 0
    dec = abs(dec)
    scaled = int((dec * (10**scale)).to_integral_value()) if scale else int(dec)

    nibble_slots = 2 * byte_length - 1
    digits = str(scaled).rjust(nibble_slots, "0")
    if len(digits) > nibble_slots:
        raise ValueError(f"value {value!r} does not fit in {byte_length} packed bytes")

    nibbles = [int(c) for c in digits] + [0xD if negative else 0xC]
    out = bytearray()
    for i in range(0, len(nibbles), 2):
        out.append((nibbles[i] << 4) | nibbles[i + 1])
    return bytes(out)


def _encode_binary(value: Any, byte_length: int, signed: bool, byte_order: str) -> bytes:
    code = _BINARY_STRUCT_CODE.get(byte_length)
    if code is None:
        raise ValueError(f"unsupported binary field width: {byte_length} bytes")
    if not signed:
        code = code.upper()
    prefix = ">" if byte_order == "big" else "<"
    return struct.pack(prefix + code, int(value))


def _encode_float(value: Any, byte_length: int, byte_order: str) -> bytes:
    code = _FLOAT_STRUCT_CODE.get(byte_length)
    if code is None:
        raise ValueError(f"unsupported float field width: {byte_length} bytes")
    prefix = ">" if byte_order == "big" else "<"
    return struct.pack(prefix + code, float(value))


def _encode_scalar(item: DataItem, value: Any, encoding: str, byte_order: str) -> bytes:
    usage = item.usage
    if usage in _UNSUPPORTED_USAGES:
        raise NotImplementedError(f"{item.name}: USAGE {usage} encoding is not supported")

    pic = item.pic
    category = pic.category if pic else None
    length = item.byte_length
    if length is None:
        raise ValueError(f"{item.name}: unknown byte length, cannot encode")

    if category in _TEXT_CATEGORIES:
        return _encode_text(value, length, encoding)

    if usage in _FLOAT_USAGES:
        return _encode_float(value, length, byte_order)

    scale = (pic.scale or 0) if pic else 0
    signed = bool(pic) and pic.raw.strip().upper().startswith("S")

    if usage in _PACKED_USAGES or category == PicCategory.PACKED_DECIMAL:
        return _encode_packed(value, length, scale)
    if usage in _BINARY_USAGES or category == PicCategory.BINARY:
        return _encode_binary(value, length, signed, byte_order)

    return _encode_zoned(value, length, signed, scale, item.sign_leading, item.sign_separate, encoding)


def _encode_element(item: DataItem, value: Any, encoding: str, byte_order: str) -> bytes:
    """Encode one occurrence of item (not multiplied by its own OCCURS)."""
    if item.is_group:
        if not isinstance(value, dict):
            raise ValueError(f"{item.name}: expected a dict of field values for this group")
        return _encode_group(item, value, encoding, byte_order)
    return _encode_scalar(item, value, encoding, byte_order)


def _encode_field(item: DataItem, value: Any, encoding: str, byte_order: str) -> bytes:
    """Encode item (handling its own OCCURS, if any)."""
    if item.occurs is None:
        return _encode_element(item, value, encoding, byte_order)
    elements = value or []
    return b"".join(_encode_element(item, v, encoding, byte_order) for v in elements)


def _static_span(item: DataItem) -> Optional[int]:
    """Full static storage span of item, its own OCCURS multiplication
    included — used to pad a REDEFINES slot to the widest sibling. None for
    variable-length items (OCCURS DEPENDING ON), which can't be padded to a
    fixed width; encode then falls back to the chosen field's actual size.
    """
    if item.byte_length is None:
        return None
    if item.occurs is None:
        return item.byte_length
    if item.occurs.max_occurs != item.occurs.min_occurs:
        return None
    return item.byte_length * item.occurs.max_occurs


def _encode_group(item: DataItem, values: dict[str, Any], encoding: str, byte_order: str) -> bytes:
    slots, orphans = group_slots(item.children)
    out = bytearray()

    for base_item, aliases in slots:
        candidates = [base_item] + aliases
        chosen = next((c for c in candidates if not c.is_filler and c.name in values), None)

        if chosen is None:
            out += b"\x00" * max((_static_span(c) or 0) for c in candidates)
            continue

        chunk = _encode_field(chosen, values[chosen.name], encoding, byte_order)
        slot_width = max([len(chunk)] + [(_static_span(c) or 0) for c in candidates])
        out += chunk.ljust(slot_width, b"\x00")

    for alias in orphans:
        if not alias.is_filler and alias.name in values:
            out += _encode_field(alias, values[alias.name], encoding, byte_order)
        else:
            out += b"\x00" * (_static_span(alias) or 0)

    return bytes(out)


def encode_record(
    item: DataItem, values: dict[str, Any], encoding: str = "cp037", byte_order: str = "big"
) -> bytes:
    """Encode a dict of field values (shaped like decode_record's output) back
    into raw record bytes, using the same offset-assigned DataItem tree.

    REDEFINES: when a slot's base field and its alias(es) share storage, the
    base field's value is written if present in `values`; otherwise the
    first alias found in `values` is written instead. Only one interpretation
    can occupy the physical bytes, so the others are ignored.

    OCCURS DEPENDING ON: the element count comes from the `depending_on`
    field's own value in `values` (not re-derived from list length) — the
    caller is responsible for keeping the count and the list in sync.

    Level 66 (RENAMES) values are ignored; write through the field(s) they
    alias instead, since they share the same physical storage.
    """
    if item.is_group:
        if not isinstance(values, dict):
            raise ValueError(f"{item.name}: expected a dict of field values")
        return _encode_group(item, values, encoding, byte_order)
    return _encode_scalar(item, values[item.name], encoding, byte_order)
