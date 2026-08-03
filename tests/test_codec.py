"""Tests for the codec layer: decoding raw record bytes into Python values."""
from __future__ import annotations

import struct
from decimal import Decimal

import pytest

from cobol_data_parser.data.codec import decode_record, encode_record, iter_records
from cobol_data_parser.data.parser import parse


def _zoned(digits: str, negative: bool = False) -> bytes:
    """Build EBCDIC (cp037) zoned-decimal bytes, over-punching the sign."""
    raw = bytearray(digits.encode("cp037"))
    zone = 0xD if negative else 0xC
    raw[-1] = (zone << 4) | (raw[-1] & 0x0F)
    return bytes(raw)


def _packed(digits: str, byte_length: int, negative: bool = False) -> bytes:
    """Build COMP-3 packed-decimal bytes for the given digit string."""
    nibble_slots = 2 * byte_length - 1
    padded = digits.rjust(nibble_slots, "0")
    nibbles = [int(c) for c in padded] + [0xD if negative else 0xC]
    out = bytearray()
    for i in range(0, len(nibbles), 2):
        out.append((nibbles[i] << 4) | nibbles[i + 1])
    return bytes(out)


def _binary(value: int, byte_length: int, signed: bool = True) -> bytes:
    code = {2: "h", 4: "i", 8: "q"}[byte_length]
    if not signed:
        code = code.upper()
    return struct.pack(">" + code, value)


# ─── DISPLAY: text and zoned decimal ─────────────────────────────────────────


def test_decode_display_text_and_zoned_numeric():
    cobol = """
    01 CUSTOMER-REC.
       05 CUST-ID   PIC 9(5).
       05 CUST-NAME PIC X(10).
       05 BALANCE   PIC S9(5)V99.
    """
    rec = parse(cobol)[0]
    buffer = (
        "12345".encode("cp037")
        + "ALICE     ".encode("cp037")
        + _zoned("0012345", negative=True)
    )

    result = decode_record(rec, buffer)
    assert result["CUST-ID"] == 12345
    assert result["CUST-NAME"] == "ALICE"
    assert result["BALANCE"] == Decimal("-123.45")


def test_decode_unsigned_display_numeric_ignores_sign_nibble():
    cobol = "01 REC.\n   05 QTY PIC 9(3).\n"
    rec = parse(cobol)[0]
    buffer = _zoned("042", negative=True)  # sign nibble set, but field is unsigned
    assert decode_record(rec, buffer)["QTY"] == 42


# ─── SIGN IS ... [SEPARATE] ───────────────────────────────────────────────────


def test_decode_sign_trailing_separate():
    cobol = "01 REC.\n   05 AMT PIC S9(5) SIGN IS TRAILING SEPARATE.\n"
    rec = parse(cobol)[0]
    assert rec.children[0].byte_length == 6  # 5 digits + 1 sign byte
    buffer = "12345".encode("cp037") + "-".encode("cp037")
    assert decode_record(rec, buffer)["AMT"] == -12345


def test_decode_sign_leading_separate():
    cobol = "01 REC.\n   05 AMT PIC S9(5) SIGN IS LEADING SEPARATE.\n"
    rec = parse(cobol)[0]
    buffer = "+".encode("cp037") + "12345".encode("cp037")
    assert decode_record(rec, buffer)["AMT"] == 12345


def test_decode_sign_leading_overpunch_not_separate():
    cobol = "01 REC.\n   05 AMT PIC S9(3) SIGN IS LEADING.\n"
    rec = parse(cobol)[0]
    assert rec.children[0].byte_length == 3  # no extra byte, still over-punched
    raw = bytearray("123".encode("cp037"))
    raw[0] = (0xD << 4) | (raw[0] & 0x0F)  # negative zone on the FIRST byte
    assert decode_record(rec, bytes(raw))["AMT"] == -123


# ─── COMP-3 packed decimal ───────────────────────────────────────────────────


def test_decode_packed_decimal():
    cobol = "01 REC.\n   05 AMOUNT PIC S9(7)V99 COMP-3.\n"
    rec = parse(cobol)[0]
    field = rec.children[0]
    assert field.byte_length == 5
    buffer = _packed("123456789", byte_length=5, negative=True)
    assert decode_record(rec, buffer)["AMOUNT"] == Decimal("-1234567.89")


def test_decode_packed_decimal_positive_no_scale():
    cobol = "01 REC.\n   05 COUNT PIC 9(3) COMP-3.\n"
    rec = parse(cobol)[0]
    field = rec.children[0]
    buffer = _packed("042", byte_length=field.byte_length)
    assert decode_record(rec, buffer)["COUNT"] == 42


# ─── COMP/BINARY ──────────────────────────────────────────────────────────────


def test_decode_binary_signed_and_unsigned():
    cobol = """
    01 REC.
       05 SIGNED-FIELD   PIC S9(4) COMP.
       05 UNSIGNED-FIELD PIC 9(4) COMP.
    """
    rec = parse(cobol)[0]
    signed_field, unsigned_field = rec.children
    assert signed_field.byte_length == 2
    buffer = _binary(-100, 2, signed=True) + _binary(200, 2, signed=False)
    result = decode_record(rec, buffer)
    assert result["SIGNED-FIELD"] == -100
    assert result["UNSIGNED-FIELD"] == 200


def test_decode_binary_little_endian_comp5():
    cobol = "01 REC.\n   05 NATIVE-FIELD PIC 9(9) COMP-5.\n"
    rec = parse(cobol)[0]
    buffer = struct.pack("<i", 123456789)
    result = decode_record(rec, buffer, byte_order="little")
    assert result["NATIVE-FIELD"] == 123456789


# ─── REDEFINES ────────────────────────────────────────────────────────────────


def test_decode_redefines_both_interpretations():
    cobol = """
    01 WORK.
       05 AS-TEXT PIC X(4).
       05 AS-NUM REDEFINES AS-TEXT PIC 9(4).
    """
    rec = parse(cobol)[0]
    buffer = "1234".encode("cp037")
    result = decode_record(rec, buffer)
    assert result["AS-TEXT"] == "1234"
    assert result["AS-NUM"] == 1234


# ─── Level 66 (RENAMES) ───────────────────────────────────────────────────────


def test_decode_renames_single_target():
    cobol = """
    01 REC.
       05 FIELD-A PIC X(5).
       05 FIELD-B PIC 9(3).
       66 ALIAS-A RENAMES FIELD-A.
    """
    rec = parse(cobol)[0]
    buffer = "HELLO123".encode("cp037")
    result = decode_record(rec, buffer)
    assert result["FIELD-A"] == "HELLO"
    assert result["ALIAS-A"] == "HELLO"


def test_decode_renames_thru_is_not_included():
    cobol = """
    01 REC.
       05 FIELD-A PIC X(5).
       05 FIELD-B PIC 9(3).
       66 COMBINED RENAMES FIELD-A THRU FIELD-B.
    """
    rec = parse(cobol)[0]
    buffer = "HELLO123".encode("cp037")
    result = decode_record(rec, buffer)
    assert "COMBINED" not in result


# ─── OCCURS (fixed) ───────────────────────────────────────────────────────────


def test_decode_fixed_occurs_elementary():
    cobol = "01 REC.\n   05 ITEM OCCURS 3 TIMES PIC 9(2).\n"
    rec = parse(cobol)[0]
    buffer = "010203".encode("cp037")
    assert decode_record(rec, buffer)["ITEM"] == [1, 2, 3]


def test_decode_fixed_occurs_group():
    cobol = """
    01 REC.
       05 LINE OCCURS 2 TIMES.
          10 LINE-ID  PIC 9(2).
          10 LINE-AMT PIC 9(3).
    """
    rec = parse(cobol)[0]
    buffer = ("01100" + "02200").encode("cp037")
    result = decode_record(rec, buffer)["LINE"]
    assert result == [{"LINE-ID": 1, "LINE-AMT": 100}, {"LINE-ID": 2, "LINE-AMT": 200}]


# ─── OCCURS DEPENDING ON: dynamic resolution beyond what layout.py can offset ─


def test_decode_odo_resolves_actual_count_and_trailing_field():
    cobol = """
    01 REC.
       05 ITEM-COUNT PIC 9(1).
       05 ITEMS OCCURS 1 TO 5 TIMES DEPENDING ON ITEM-COUNT PIC X(2).
       05 TRAILER PIC X(3).
    """
    rec = parse(cobol)[0]
    trailer = rec.children[2]
    assert trailer.offset is None  # static layout can't know this

    # 2 items -> ITEMS occupies 4 bytes, TRAILER starts right after
    buffer = "2".encode("cp037") + "AABB".encode("cp037") + "END".encode("cp037")
    result = decode_record(rec, buffer)
    assert result["ITEM-COUNT"] == 2
    assert result["ITEMS"] == ["AA", "BB"]
    assert result["TRAILER"] == "END"

    # Same copybook, different count -> TRAILER's real position shifts too
    buffer2 = "3".encode("cp037") + "AABBCC".encode("cp037") + "END".encode("cp037")
    result2 = decode_record(rec, buffer2)
    assert result2["ITEMS"] == ["AA", "BB", "CC"]
    assert result2["TRAILER"] == "END"


def test_decode_odo_group():
    cobol = """
    01 REC.
       05 CNT PIC 9(1).
       05 ROWS OCCURS 1 TO 3 TIMES DEPENDING ON CNT.
          10 ROW-ID PIC 9(1).
    """
    rec = parse(cobol)[0]
    buffer = "2".encode("cp037") + "79".encode("cp037")
    result = decode_record(rec, buffer)
    assert result["ROWS"] == [{"ROW-ID": 7}, {"ROW-ID": 9}]


# ─── Encoding (the inverse of decoding) ──────────────────────────────────────


def test_encode_decode_round_trip_mixed_types():
    cobol = """
    01 CUSTOMER-REC.
       05 CUST-ID   PIC 9(5).
       05 CUST-NAME PIC X(10).
       05 BALANCE   PIC S9(5)V99.
       05 RATE      USAGE COMP-1.
       05 QTY       PIC S9(4) COMP.
       05 AMT       PIC S9(7)V99 COMP-3.
    """
    rec = parse(cobol)[0]
    values = {
        "CUST-ID": 12345,
        "CUST-NAME": "ALICE",
        "BALANCE": Decimal("-123.45"),
        "RATE": 3.140000104904175,
        "QTY": -100,
        "AMT": Decimal("-1234567.89"),
    }
    encoded = encode_record(rec, values)
    assert len(encoded) == rec.byte_length
    assert decode_record(rec, encoded) == values


def test_encode_text_pads_with_spaces():
    cobol = "01 REC.\n   05 NAME PIC X(10).\n"
    rec = parse(cobol)[0]
    encoded = encode_record(rec, {"NAME": "AB"})
    assert decode_record(rec, encoded)["NAME"] == "AB"
    assert len(encoded) == 10


def test_encode_text_too_long_raises():
    cobol = "01 REC.\n   05 NAME PIC X(3).\n"
    rec = parse(cobol)[0]
    with pytest.raises(ValueError):
        encode_record(rec, {"NAME": "TOOLONG"})


def test_encode_fixed_occurs():
    cobol = "01 REC.\n   05 ITEM OCCURS 3 TIMES PIC 9(2).\n"
    rec = parse(cobol)[0]
    encoded = encode_record(rec, {"ITEM": [1, 2, 3]})
    assert decode_record(rec, encoded)["ITEM"] == [1, 2, 3]


def test_encode_fixed_occurs_group():
    cobol = """
    01 REC.
       05 LINE OCCURS 2 TIMES.
          10 LINE-ID  PIC 9(2).
          10 LINE-AMT PIC 9(3).
    """
    rec = parse(cobol)[0]
    values = {"LINE": [{"LINE-ID": 1, "LINE-AMT": 100}, {"LINE-ID": 2, "LINE-AMT": 200}]}
    encoded = encode_record(rec, values)
    assert decode_record(rec, encoded)["LINE"] == values["LINE"]


def test_encode_occurs_depending_on_uses_caller_supplied_count():
    cobol = """
    01 REC.
       05 ITEM-COUNT PIC 9(1).
       05 ITEMS OCCURS 1 TO 5 TIMES DEPENDING ON ITEM-COUNT PIC X(2).
       05 TRAILER PIC X(3).
    """
    rec = parse(cobol)[0]
    values = {"ITEM-COUNT": 2, "ITEMS": ["AA", "BB"], "TRAILER": "END"}
    encoded = encode_record(rec, values)
    assert decode_record(rec, encoded) == values


def test_encode_redefines_writes_base_field_when_present():
    cobol = """
    01 WORK.
       05 AS-TEXT PIC X(4).
       05 AS-NUM REDEFINES AS-TEXT PIC 9(4).
    """
    rec = parse(cobol)[0]
    encoded = encode_record(rec, {"AS-TEXT": "1234"})
    assert decode_record(rec, encoded) == {"AS-TEXT": "1234", "AS-NUM": 1234}


def test_encode_redefines_writes_alias_when_base_absent():
    cobol = """
    01 WORK.
       05 AS-TEXT PIC X(4).
       05 AS-NUM REDEFINES AS-TEXT PIC 9(4).
    """
    rec = parse(cobol)[0]
    encoded = encode_record(rec, {"AS-NUM": 1234})
    assert decode_record(rec, encoded) == {"AS-TEXT": "1234", "AS-NUM": 1234}


def test_encode_sign_separate_round_trip():
    cobol = "01 REC.\n   05 AMT PIC S9(5) SIGN IS LEADING SEPARATE.\n"
    rec = parse(cobol)[0]
    encoded = encode_record(rec, {"AMT": -12345})
    assert decode_record(rec, encoded)["AMT"] == -12345
    assert len(encoded) == 6


def test_encode_comp1_comp2_round_trip():
    cobol = "01 REC.\n   05 SINGLE-VAL USAGE COMP-1.\n   05 DOUBLE-VAL USAGE COMP-2.\n"
    rec = parse(cobol)[0]
    encoded = encode_record(rec, {"SINGLE-VAL": 1.5, "DOUBLE-VAL": 2.5})
    result = decode_record(rec, encoded)
    assert result["SINGLE-VAL"] == pytest.approx(1.5)
    assert result["DOUBLE-VAL"] == pytest.approx(2.5)


# ─── iter_records ─────────────────────────────────────────────────────────────


def test_iter_records_splits_fixed_length_stream():
    cobol = "01 REC.\n   05 ID PIC 9(3).\n"
    rec = parse(cobol)[0]
    data = "001".encode("cp037") + "002".encode("cp037") + "003".encode("cp037")
    results = list(iter_records(rec, data))
    assert [r["ID"] for r in results] == [1, 2, 3]


def test_iter_records_rejects_variable_length_without_explicit_length():
    cobol = """
    01 REC.
       05 CNT PIC 9(1).
       05 ITEMS OCCURS 1 TO 3 TIMES DEPENDING ON CNT PIC X(1).
    """
    rec = parse(cobol)[0]
    with pytest.raises(ValueError):
        list(iter_records(rec, b"1A2AB"))


# ─── COMP-1/COMP-2 floating point ────────────────────────────────────────────


def test_decode_comp1_single_precision_float():
    cobol = "01 REC.\n   05 RATE USAGE COMP-1.\n"
    rec = parse(cobol)[0]
    buffer = struct.pack(">f", 3.14)
    result = decode_record(rec, buffer)
    assert result["RATE"] == pytest.approx(3.14, rel=1e-6)


def test_decode_comp2_double_precision_float():
    cobol = "01 REC.\n   05 RATE USAGE COMP-2.\n"
    rec = parse(cobol)[0]
    buffer = struct.pack(">d", 2.718281828)
    result = decode_record(rec, buffer)
    assert result["RATE"] == pytest.approx(2.718281828)


def test_decode_comp1_little_endian():
    cobol = "01 REC.\n   05 RATE USAGE COMP-1.\n"
    rec = parse(cobol)[0]
    buffer = struct.pack("<f", -1.5)
    result = decode_record(rec, buffer, byte_order="little")
    assert result["RATE"] == pytest.approx(-1.5)


# ─── Unsupported usages ───────────────────────────────────────────────────────


def test_decode_index_raises_not_implemented():
    cobol = "01 REC.\n   05 PTR USAGE INDEX.\n"
    rec = parse(cobol)[0]
    with pytest.raises(NotImplementedError):
        decode_record(rec, b"\x00\x00\x00\x00")
