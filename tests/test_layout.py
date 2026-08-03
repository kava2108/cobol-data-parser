"""Tests for AST normalization: byte offset assignment across the tree."""
from __future__ import annotations

from cobol_data_parser.data.parser import parse


def test_sequential_offsets():
    cobol = """
    01 CUSTOMER-REC.
       05 CUST-ID        PIC 9(5).
       05 CUST-NAME.
          10 FIRST-NAME  PIC X(10).
          10 LAST-NAME   PIC X(10).
       05 BALANCE        PIC S9(7)V99.
    """
    rec = parse(cobol)[0]
    cust_id, cust_name, balance = rec.children
    first_name, last_name = cust_name.children

    assert rec.offset == 0
    assert cust_id.offset == 0
    assert cust_name.offset == 5
    assert first_name.offset == 5
    assert last_name.offset == 15
    assert balance.offset == 25
    assert rec.byte_length == 34  # 5 + 10 + 10 + 9
    assert cust_name.byte_length == 20


def test_redefines_shares_offset_of_target():
    cobol = """
    01 WORK.
       05 ORIG PIC X(8).
       05 ALT REDEFINES ORIG PIC S9(9)V99 COMP-3.
       05 AFTER PIC X(3).
    """
    orig, alt, after = parse(cobol)[0].children
    assert orig.offset == 0
    assert alt.offset == 0  # shares ORIG's offset, doesn't advance the cursor
    # slot width is max(len(ORIG)=8, len(ALT)=6) -> cursor advances by 8
    assert after.offset == 8


def test_redefines_alias_wider_than_target_widens_slot():
    cobol = """
    01 WORK.
       05 ORIG PIC X(4).
       05 ALT REDEFINES ORIG PIC X(10).
       05 AFTER PIC X(1).
    """
    orig, alt, after = parse(cobol)[0].children
    assert orig.offset == 0
    assert alt.offset == 0
    assert after.offset == 10  # slot width = max(4, 10)


def test_occurs_multiplies_element_span():
    cobol = """
    01 TABLE-REC.
       05 ITEM OCCURS 10 TIMES PIC X(5).
       05 AFTER PIC X(1).
    """
    item, after = parse(cobol)[0].children
    assert item.offset == 0
    assert item.byte_length == 5  # per-element size, not multiplied
    assert after.offset == 50  # 5 * 10


def test_group_occurs_multiplies_group_span():
    cobol = """
    01 MASTER-REC.
       05 ORDER-LINES OCCURS 5 TIMES.
          10 ORDER-ID  PIC 9(7).
          10 ORDER-AMT PIC S9(7)V99 COMP-3.
       05 AFTER PIC X(1).
    """
    order_lines, after = parse(cobol)[0].children
    order_id, order_amt = order_lines.children
    assert order_id.offset == 0
    assert order_amt.offset == 7
    assert order_lines.byte_length == 12  # one row: 7 + 5 (packed digits=9 -> floor(9/2)+1=5 bytes)
    assert after.offset == 60  # 12 * 5


def test_renames_single_target_borrows_offset_and_pic():
    cobol = """
    01 REC.
       05 FIELD-A PIC X(5).
       05 FIELD-B PIC 9(3).
       66 ALIAS-A RENAMES FIELD-A.
    """
    field_a, field_b, alias_a = parse(cobol)[0].children
    assert alias_a.level == 66
    assert alias_a.offset == field_a.offset == 0
    assert alias_a.byte_length == field_a.byte_length == 5
    assert alias_a.pic.raw == field_a.pic.raw


def test_renames_thru_spans_combined_length_with_no_pic():
    cobol = """
    01 REC.
       05 FIELD-A PIC X(5).
       05 FIELD-B PIC 9(3).
       05 FIELD-C PIC 9(2).
       66 COMBINED RENAMES FIELD-A THRU FIELD-C.
    """
    field_a, field_b, field_c, combined = parse(cobol)[0].children
    assert combined.offset == field_a.offset == 0
    assert combined.byte_length == 10  # 5 + 3 + 2
    assert combined.pic is None


def test_odo_leaves_trailing_offsets_unknown():
    cobol = """
    01 MASTER-REC.
       05 ITEM-COUNT PIC 9(3).
       05 ITEMS OCCURS 1 TO 100 TIMES DEPENDING ON ITEM-COUNT PIC X(5).
       05 AFTER PIC X(1).
    """
    item_count, items, after = parse(cobol)[0].children
    assert item_count.offset == 0
    assert items.offset == 3  # still known: starts right after ITEM-COUNT
    assert after.offset is None  # length of ITEMS is data-dependent
    assert parse(cobol)[0].byte_length is None  # record's own total size is variable
