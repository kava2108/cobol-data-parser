import json

import pytest

from cobol_data_parser.emitter import emit, to_json
from cobol_data_parser.parser import parse


def _parse_emit(cobol: str) -> dict:
    return emit(parse(cobol))


def test_exact_output_matches_spec():
    cobol = """
    01 CUSTOMER-REC.
       05 CUST-ID        PIC 9(5).
       05 CUST-NAME.
          10 FIRST-NAME  PIC X(10).
          10 LAST-NAME   PIC X(10).
       05 BALANCE        PIC S9(7)V99.
    """
    result = _parse_emit(cobol)
    assert result == {
        "CUSTOMER-REC": {
            "CUST-ID": {"type": "numeric", "length": 5},
            "CUST-NAME": {
                "FIRST-NAME": {"type": "string", "length": 10},
                "LAST-NAME": {"type": "string", "length": 10},
            },
            "BALANCE": {"type": "signed-decimal", "precision": 7, "scale": 2},
        }
    }


def test_filler_excluded():
    cobol = """
    01 MY-REC.
       05 FILLER PIC X(5).
       05 NAME   PIC X(10).
    """
    rec = _parse_emit(cobol)["MY-REC"]
    assert "FILLER" not in rec
    assert "NAME" in rec


def test_88_level_excluded():
    cobol = """
    01 MY-REC.
       05 STATUS PIC 9(2).
          88 ACTIVE VALUE 1.
    """
    rec = _parse_emit(cobol)["MY-REC"]
    assert "STATUS" in rec
    assert rec["STATUS"] == {"type": "numeric", "length": 2}


def test_packed_decimal_usage():
    cobol = """
    01 FIN-REC.
       05 AMOUNT PIC S9(9)V99 COMP-3.
    """
    amount = _parse_emit(cobol)["FIN-REC"]["AMOUNT"]
    assert amount["type"] == "packed-decimal"
    assert amount["usage"] == "COMP-3"
    assert amount["precision"] == 9
    assert amount["scale"] == 2


def test_display_usage_omitted():
    cobol = """
    01 MY-REC.
       05 FIELD-A PIC X(5) DISPLAY.
    """
    field = _parse_emit(cobol)["MY-REC"]["FIELD-A"]
    assert "usage" not in field


def test_redefines_union_in_output():
    cobol = """
    01 WORK.
       05 ORIG PIC 9(5).
       05 ALT REDEFINES ORIG PIC X(5).
    """
    work = _parse_emit(cobol)["WORK"]
    # ALT is folded into ORIG's union; it must not appear as a sibling
    assert "ALT" not in work
    assert "union" in work["ORIG"]
    alt = work["ORIG"]["union"][0]
    assert alt["name"] == "ALT"
    assert alt["type"] == "string"
    assert alt["length"] == 5


def test_elementary_occurs():
    cobol = """
    01 TABLE-REC.
       05 ITEM OCCURS 10 TIMES PIC X(5).
    """
    item = _parse_emit(cobol)["TABLE-REC"]["ITEM"]
    assert item["occurs"] == 10
    assert item["type"] == "string"


def test_group_occurs_uses_fields_envelope():
    cobol = """
    01 MASTER.
       05 LINES OCCURS 5 TIMES.
          10 LINE-ID  PIC 9(5).
          10 LINE-AMT PIC S9(7)V99.
    """
    lines = _parse_emit(cobol)["MASTER"]["LINES"]
    assert lines["occurs"] == 5
    assert "fields" in lines
    assert "LINE-ID" in lines["fields"]
    assert "LINE-AMT" in lines["fields"]


def test_to_json_is_valid():
    cobol = """
    01 SIMPLE-REC.
       05 FIELD-A PIC X(5).
    """
    result = to_json(parse(cobol))
    parsed = json.loads(result)
    assert "SIMPLE-REC" in parsed


def test_multiple_records():
    cobol = """
    01 REC-A.
       05 FA PIC X(5).
    01 REC-B.
       05 FB PIC 9(3).
    """
    result = _parse_emit(cobol)
    assert "REC-A" in result
    assert "REC-B" in result
