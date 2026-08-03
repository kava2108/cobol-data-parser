"""Tests for the Markdown data-item definition table generator."""
from __future__ import annotations

from cobol_data_parser.data.docgen import to_markdown_table
from cobol_data_parser.data.parser import parse


def _cell(line: str, index: int) -> str:
    # Strip only ASCII spaces (the table's cell padding) — full-width indent
    # spaces (U+3000) inside the Level column must survive, since
    # str.strip() with no args also treats U+3000 as whitespace.
    return [c.strip(" ") for c in line.strip(" ").strip("|").split("|")][index]


def test_header_and_separator():
    items = parse("01 REC.\n   05 FIELD-A PIC X(5).\n")
    lines = to_markdown_table(items).splitlines()
    assert lines[0].startswith("| Level | 項目名 | PIC |")
    assert lines[1].startswith("|---|")


def test_flat_record_row_values():
    cobol = """
    01 CUSTOMER-REC.
       05 CUST-ID PIC 9(5).
    """
    items = parse(cobol)
    lines = to_markdown_table(items).splitlines()
    root_row, field_row = lines[2], lines[3]

    assert _cell(root_row, 0) == "01"
    assert _cell(root_row, 1) == "CUSTOMER-REC"
    assert _cell(root_row, 5) == "5"  # bytes
    assert _cell(root_row, 6) == "0"  # offset

    assert _cell(field_row, 1) == "CUST-ID"
    assert _cell(field_row, 2) == "9(5)"
    assert _cell(field_row, 4) == "5"  # digits
    assert _cell(field_row, 5) == "5"  # bytes
    assert _cell(field_row, 6) == "0"  # offset


def test_nesting_uses_indentation():
    cobol = """
    01 REC.
       05 GROUP-A.
          10 CHILD PIC X(1).
    """
    items = parse(cobol)
    lines = to_markdown_table(items).splitlines()
    child_row = lines[4]
    assert _cell(child_row, 0) == "　　　　10"  # depth 2 -> 4 full-width spaces


def test_decimal_digits_shown_as_precision_scale():
    cobol = "01 REC.\n   05 BALANCE PIC S9(7)V99.\n"
    items = parse(cobol)
    lines = to_markdown_table(items).splitlines()
    assert _cell(lines[3], 4) == "7,2"


def test_text_field_has_no_digits_cell():
    cobol = "01 REC.\n   05 NAME PIC X(10).\n"
    items = parse(cobol)
    lines = to_markdown_table(items).splitlines()
    assert _cell(lines[3], 4) == ""
    assert _cell(lines[3], 5) == "10"  # bytes still shown


def test_usage_column():
    cobol = "01 REC.\n   05 AMOUNT PIC S9(9)V99 COMP-3.\n"
    items = parse(cobol)
    lines = to_markdown_table(items).splitlines()
    assert _cell(lines[3], 3) == "COMP-3"


def test_redefines_column():
    cobol = """
    01 REC.
       05 ORIG PIC X(5).
       05 ALT REDEFINES ORIG PIC 9(5).
    """
    items = parse(cobol)
    lines = to_markdown_table(items).splitlines()
    alt_row = lines[4]
    assert _cell(alt_row, 1) == "ALT"
    assert _cell(alt_row, 7) == "ORIG"
    assert _cell(alt_row, 6) == "0"  # shares ORIG's offset


def test_occurs_column_fixed_and_variable():
    cobol = """
    01 REC.
       05 CNT PIC 9(2).
       05 ITEMS OCCURS 1 TO 10 TIMES DEPENDING ON CNT PIC X(1).
       05 TABLE-ITEM OCCURS 5 TIMES PIC X(1).
    """
    items = parse(cobol)
    lines = to_markdown_table(items).splitlines()
    assert _cell(lines[4], 8) == "1〜10 (CNT)"
    assert _cell(lines[5], 8) == "5"


def test_filler_and_88_level_are_included():
    cobol = """
    01 REC.
       05 FILLER PIC X(5).
       05 STATUS PIC 9(1).
          88 ACTIVE VALUE 1.
    """
    items = parse(cobol)
    table = to_markdown_table(items)
    assert "FILLER" in table
    assert "ACTIVE" in table


def test_renames_shown_in_name_cell():
    cobol = """
    01 REC.
       05 FIELD-A PIC X(5).
       05 FIELD-B PIC 9(3).
       66 ALIAS-A RENAMES FIELD-A.
       66 COMBINED RENAMES FIELD-A THRU FIELD-B.
    """
    items = parse(cobol)
    lines = to_markdown_table(items).splitlines()
    assert _cell(lines[5], 1) == "ALIAS-A（RENAMES FIELD-A）"
    assert _cell(lines[6], 1) == "COMBINED（RENAMES FIELD-A THRU FIELD-B）"


def test_unknown_offset_is_blank_not_none_string():
    cobol = """
    01 REC.
       05 CNT PIC 9(1).
       05 ITEMS OCCURS 1 TO 3 TIMES DEPENDING ON CNT PIC X(1).
       05 AFTER PIC X(1).
    """
    items = parse(cobol)
    lines = to_markdown_table(items).splitlines()
    after_row = lines[5]
    assert _cell(after_row, 1) == "AFTER"
    assert _cell(after_row, 6) == ""
    assert "None" not in after_row
