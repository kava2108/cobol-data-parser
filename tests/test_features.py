"""Tests for COPYBOOK expansion, REDEFINES graph, and OCCURS DEPENDING ON."""
from __future__ import annotations

import warnings

import pytest

from cobol_data_parser.emitter import emit
from cobol_data_parser.parser import parse


# ─── OCCURS DEPENDING ON ─────────────────────────────────────────────────────


def test_odo_parse_attributes():
    cobol = """
    01 MASTER-REC.
       05 ITEM-COUNT PIC 9(3).
       05 ITEMS OCCURS 1 TO 100 TIMES DEPENDING ON ITEM-COUNT.
          10 ITEM-ID  PIC 9(5).
          10 ITEM-AMT PIC S9(7)V99.
    """
    items_field = parse(cobol)[0].children[1]
    oc = items_field.occurs
    assert oc.min_occurs == 1
    assert oc.max_occurs == 100
    assert oc.depending_on == "ITEM-COUNT"
    assert oc.is_variable is True


def test_odo_emit_group():
    cobol = """
    01 MASTER-REC.
       05 ITEM-COUNT PIC 9(3).
       05 ITEMS OCCURS 1 TO 100 TIMES DEPENDING ON ITEM-COUNT.
          10 ITEM-ID  PIC 9(5).
          10 ITEM-AMT PIC S9(7)V99.
    """
    node = emit(parse(cobol))["MASTER-REC"]["ITEMS"]
    assert node["occurs"] == {"min": 1, "max": 100, "depending_on": "ITEM-COUNT"}
    assert "fields" in node
    assert "ITEM-ID" in node["fields"]
    assert "ITEM-AMT" in node["fields"]


def test_odo_emit_elementary():
    cobol = """
    01 MY-REC.
       05 N PIC 9(2).
       05 CHARS OCCURS 1 TO 50 TIMES DEPENDING ON N PIC X(1).
    """
    chars = emit(parse(cobol))["MY-REC"]["CHARS"]
    assert chars["occurs"] == {"min": 1, "max": 50, "depending_on": "N"}
    assert chars["type"] == "string"


def test_fixed_occurs_still_emits_int():
    cobol = """
    01 TABLE-REC.
       05 ITEM OCCURS 10 TIMES PIC X(5).
    """
    item = emit(parse(cobol))["TABLE-REC"]["ITEM"]
    assert item["occurs"] == 10  # plain int, not a dict


def test_odo_depending_on_uppercase():
    cobol = """
    01 REC.
       05 cnt PIC 9(2).
       05 ARR OCCURS 1 TO 10 TIMES DEPENDING ON cnt PIC X.
    """
    arr_field = parse(cobol)[0].children[1]
    assert arr_field.occurs.depending_on == "CNT"


# ─── REDEFINES グラフ ─────────────────────────────────────────────────────────


def test_redefines_single_alias_folded_into_union():
    cobol = """
    01 WORK.
       05 ORIG PIC X(10).
       05 ALT REDEFINES ORIG PIC 9(10).
    """
    work = emit(parse(cobol))["WORK"]
    assert "ALT" not in work, "alias must not appear as sibling"
    assert "union" in work["ORIG"]
    assert work["ORIG"]["union"][0]["name"] == "ALT"
    assert work["ORIG"]["union"][0]["type"] == "numeric"


def test_redefines_multiple_aliases():
    cobol = """
    01 WORK.
       05 AMOUNT-DISPLAY PIC X(8).
       05 AMOUNT-PACKED REDEFINES AMOUNT-DISPLAY PIC S9(9)V99 COMP-3.
       05 AMOUNT-BINARY REDEFINES AMOUNT-DISPLAY PIC S9(9) COMP.
    """
    display = emit(parse(cobol))["WORK"]["AMOUNT-DISPLAY"]
    assert len(display["union"]) == 2
    names = [m["name"] for m in display["union"]]
    assert "AMOUNT-PACKED" in names
    assert "AMOUNT-BINARY" in names
    # Neither alias should leak to sibling level
    work_keys = emit(parse(cobol))["WORK"].keys()
    assert "AMOUNT-PACKED" not in work_keys
    assert "AMOUNT-BINARY" not in work_keys


def test_redefines_group_alias_has_fields_key():
    cobol = """
    01 WORK.
       05 ORIG PIC X(8).
       05 ALT REDEFINES ORIG.
          10 FIRST  PIC X(4).
          10 SECOND PIC X(4).
    """
    union = emit(parse(cobol))["WORK"]["ORIG"]["union"]
    alt_member = next(m for m in union if m["name"] == "ALT")
    assert "fields" in alt_member
    assert "FIRST" in alt_member["fields"]
    assert "SECOND" in alt_member["fields"]


def test_redefines_preserves_base_type():
    cobol = """
    01 WORK.
       05 ORIG PIC 9(5).
       05 ALT REDEFINES ORIG PIC X(5).
    """
    orig = emit(parse(cobol))["WORK"]["ORIG"]
    assert orig["type"] == "numeric"
    assert orig["length"] == 5


def test_redefines_alias_attributes_in_union():
    cobol = """
    01 WORK.
       05 ORIG PIC X(8).
       05 ALT REDEFINES ORIG PIC S9(9)V99 COMP-3.
    """
    alt = emit(parse(cobol))["WORK"]["ORIG"]["union"][0]
    assert alt["name"] == "ALT"
    assert alt["type"] == "packed-decimal"
    assert alt["precision"] == 9
    assert alt["scale"] == 2
    assert alt["usage"] == "COMP-3"


def test_redefines_not_in_parser_tree():
    """Parser itself still records the redefines attribute on DataItem."""
    cobol = """
    01 WORK.
       05 ORIG PIC 9(5).
       05 ALT REDEFINES ORIG PIC X(5).
    """
    children = parse(cobol)[0].children
    assert children[1].name == "ALT"
    assert children[1].redefines == "ORIG"


# ─── COPYBOOK 展開 ─────────────────────────────────────────────────────────────


def test_copybook_basic_expansion(tmp_path):
    cpy = tmp_path / "CUST-COMMON.cpy"
    cpy.write_text("05 CUST-ID PIC 9(5).\n05 CUST-NAME PIC X(20).\n")

    cobol = "01 CUSTOMER-REC.\n   COPY CUST-COMMON.\n   05 BALANCE PIC S9(7)V99.\n"
    items = parse(cobol, copybook_dirs=[tmp_path])

    assert len(items) == 1
    children = items[0].children
    assert len(children) == 3
    assert children[0].name == "CUST-ID"
    assert children[1].name == "CUST-NAME"
    assert children[2].name == "BALANCE"


def test_copybook_fields_have_correct_types(tmp_path):
    cpy = tmp_path / "ADDR.cpy"
    cpy.write_text(
        "05 STREET PIC X(30).\n"
        "05 CITY   PIC X(20).\n"
        "05 ZIP    PIC 9(5).\n"
    )
    cobol = "01 CUST-REC.\n   COPY ADDR.\n"
    items = parse(cobol, copybook_dirs=[tmp_path])
    children = items[0].children

    from cobol_data_parser.models import PicCategory
    assert children[0].name == "STREET"
    assert children[0].pic.category == PicCategory.STRING
    assert children[2].name == "ZIP"
    assert children[2].pic.category == PicCategory.NUMERIC


def test_copybook_not_found_emits_warning(tmp_path):
    cobol = "01 MY-REC.\n   COPY NONEXISTENT.\n   05 FIELD PIC X(5).\n"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        items = parse(cobol, copybook_dirs=[tmp_path])
    assert any("NONEXISTENT" in str(warning.message) for warning in w)
    # The unexpanded COPY entry is kept; FIELD is still parsed
    assert items[0].children[-1].name == "FIELD"


def test_copybook_replacing_pseudo_text(tmp_path):
    cpy = tmp_path / "GENERIC.cpy"
    cpy.write_text("05 :PREFIX:-ID   PIC 9(5).\n05 :PREFIX:-NAME PIC X(20).\n")

    cobol = "01 CUST-REC.\n   COPY GENERIC REPLACING ==:PREFIX:== BY ==CUST==.\n"
    items = parse(cobol, copybook_dirs=[tmp_path])

    children = items[0].children
    assert children[0].name == "CUST-ID"
    assert children[1].name == "CUST-NAME"


def test_copybook_multiple_dirs(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_b / "SHARED.cpy").write_text("05 X PIC X(1).\n")

    cobol = "01 MY-REC.\n   COPY SHARED.\n"
    items = parse(cobol, copybook_dirs=[dir_a, dir_b])
    assert items[0].children[0].name == "X"


def test_copybook_nested(tmp_path):
    """A copybook that itself contains a COPY statement."""
    inner = tmp_path / "INNER.cpy"
    inner.write_text("10 INNER-FIELD PIC X(5).\n")

    outer = tmp_path / "OUTER.cpy"
    outer.write_text("05 OUTER-GROUP.\n   COPY INNER.\n")

    cobol = "01 MY-REC.\n   COPY OUTER.\n"
    items = parse(cobol, copybook_dirs=[tmp_path])

    outer_group = items[0].children[0]
    assert outer_group.name == "OUTER-GROUP"
    assert outer_group.children[0].name == "INNER-FIELD"


def test_no_copybook_dirs_ignores_copy_entries():
    """Without copybook_dirs, COPY entries pass through but are dropped by _parse_entry."""
    cobol = "01 MY-REC.\n   COPY SOMETHING.\n   05 REAL-FIELD PIC X(5).\n"
    items = parse(cobol)  # no copybook_dirs
    assert items[0].children[0].name == "REAL-FIELD"
