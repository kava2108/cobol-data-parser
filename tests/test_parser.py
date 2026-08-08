import pytest

from cobol_data_parser.data.models import PicCategory
from cobol_data_parser.data.parser import parse

SIMPLE = """
01 CUSTOMER-REC.
   05 CUST-ID        PIC 9(5).
   05 CUST-NAME.
      10 FIRST-NAME  PIC X(10).
      10 LAST-NAME   PIC X(10).
   05 BALANCE        PIC S9(7)V99.
"""


def test_root_count():
    items = parse(SIMPLE)
    assert len(items) == 1


def test_root_name():
    items = parse(SIMPLE)
    assert items[0].name == "CUSTOMER-REC"
    assert items[0].level == 1


def test_root_is_group():
    items = parse(SIMPLE)
    assert items[0].is_group is True


def test_top_children_count():
    items = parse(SIMPLE)
    assert len(items[0].children) == 3


def test_elementary_pic_numeric():
    cust_id = parse(SIMPLE)[0].children[0]
    assert cust_id.name == "CUST-ID"
    assert cust_id.pic.category == PicCategory.NUMERIC
    assert cust_id.pic.length == 5


def test_nested_group():
    cust_name = parse(SIMPLE)[0].children[1]
    assert cust_name.name == "CUST-NAME"
    assert cust_name.is_group is True
    names = [c.name for c in cust_name.children]
    assert names == ["FIRST-NAME", "LAST-NAME"]


def test_signed_decimal():
    balance = parse(SIMPLE)[0].children[2]
    assert balance.name == "BALANCE"
    assert balance.pic.category == PicCategory.SIGNED_DECIMAL
    assert balance.pic.precision == 7
    assert balance.pic.scale == 2


def test_redefines():
    cobol = """
    01 WORK-AREA.
       05 ORIG-FIELD PIC 9(5).
       05 ALT-FIELD REDEFINES ORIG-FIELD PIC X(5).
    """
    children = parse(cobol)[0].children
    assert children[1].name == "ALT-FIELD"
    assert children[1].redefines == "ORIG-FIELD"
    assert children[1].pic.category == PicCategory.STRING


def test_occurs():
    cobol = """
    01 TABLE-REC.
       05 TABLE-ITEM OCCURS 10 TIMES PIC X(5).
    """
    child = parse(cobol)[0].children[0]
    assert child.name == "TABLE-ITEM"
    assert child.occurs.max_occurs == 10
    assert child.occurs.min_occurs == 10
    assert child.occurs.depending_on is None
    assert child.occurs.is_variable is False


def test_usage_comp3_overrides_category():
    cobol = """
    01 WORK-ITEM.
       05 AMOUNT PIC S9(9)V99 COMP-3.
    """
    amount = parse(cobol)[0].children[0]
    assert amount.usage == "COMP-3"
    assert amount.pic.category == PicCategory.PACKED_DECIMAL


def test_usage_comp_binary():
    cobol = """
    01 BIN-REC.
       05 BIN-FIELD PIC 9(4) COMP.
    """
    field = parse(cobol)[0].children[0]
    assert field.pic.category == PicCategory.BINARY


def test_77_level_is_root():
    cobol = """
    01 SOME-REC.
       05 FIELD-A PIC X.
    77 WORK-FIELD PIC X(10).
    """
    items = parse(cobol)
    assert len(items) == 2
    assert items[1].level == 77
    assert items[1].name == "WORK-FIELD"


def test_88_level_does_not_make_parent_group():
    cobol = """
    01 MY-REC.
       05 STATUS-CODE PIC 9(2).
          88 ACTIVE   VALUE 1.
          88 INACTIVE VALUE 0.
    """
    status = parse(cobol)[0].children[0]
    assert status.name == "STATUS-CODE"
    # 88-level children exist but is_group should be False
    assert status.is_group is False
    assert status.pic.category == PicCategory.NUMERIC


def test_filler_is_parsed():
    cobol = """
    01 MY-REC.
       05 FILLER PIC X(5).
       05 NAME   PIC X(10).
    """
    children = parse(cobol)[0].children
    assert children[0].is_filler is True
    assert children[1].is_filler is False


def test_fixed_format():
    cobol = (
        "000010 01 FIXED-REC.                                               \n"
        "000020    05 FIELD-A        PIC X(10).                             \n"
        "000030    05 FIELD-B        PIC 9(5).                              \n"
    )
    items = parse(cobol, fixed_format=True)
    assert len(items) == 1
    assert items[0].name == "FIXED-REC"
    children = items[0].children
    assert len(children) == 2
    assert children[0].name == "FIELD-A"


def test_multiple_01_records():
    cobol = """
    01 REC-A.
       05 FA PIC X(5).
    01 REC-B.
       05 FB PIC 9(3).
    """
    items = parse(cobol)
    assert len(items) == 2
    assert items[0].name == "REC-A"
    assert items[1].name == "REC-B"


def test_group_occurs():
    cobol = """
    01 MASTER-REC.
       05 ORDER-LINES OCCURS 5 TIMES.
          10 ORDER-ID  PIC 9(7).
          10 ORDER-AMT PIC S9(7)V99 COMP-3.
    """
    order_lines = parse(cobol)[0].children[0]
    assert order_lines.name == "ORDER-LINES"
    assert order_lines.occurs.max_occurs == 5
    assert order_lines.is_group is True
    assert len(order_lines.children) == 2


def test_sign_clause_defaults_to_trailing_overpunch():
    cobol = "01 REC.\n   05 AMT PIC S9(5).\n"
    item = parse(cobol)[0].children[0]
    assert item.sign_separate is False
    assert item.sign_leading is False


def test_sign_is_leading_separate():
    cobol = "01 REC.\n   05 AMT PIC S9(5) SIGN IS LEADING SEPARATE CHARACTER.\n"
    item = parse(cobol)[0].children[0]
    assert item.sign_leading is True
    assert item.sign_separate is True
    assert item.byte_length == 6


def test_sign_is_trailing_without_separate():
    cobol = "01 REC.\n   05 AMT PIC S9(5) SIGN IS TRAILING.\n"
    item = parse(cobol)[0].children[0]
    assert item.sign_leading is False
    assert item.sign_separate is False
    assert item.byte_length == 5


def test_pic_with_embedded_decimal_point_not_truncated_at_terminator():
    """PIC's own explicit decimal point (e.g. ZZZ,ZZ9.99) must not be
    mistaken for the entry's terminating period."""
    cobol = "01 REC.\n   05 AMT PIC ZZZ,ZZ9.99.\n"
    item = parse(cobol)[0].children[0]
    assert item.pic.category == PicCategory.NUMERIC_EDITED
    assert item.pic.length == 10
    assert item.pic.edit_symbols == ["Z", ",", "."]


def test_pic_with_decimal_point_followed_by_other_clause():
    cobol = "01 REC.\n   05 AMT PIC ZZZ,ZZ9.99 USAGE DISPLAY.\n"
    item = parse(cobol)[0].children[0]
    assert item.pic.length == 10
    assert item.pic.edit_symbols == ["Z", ",", "."]


def test_hyphenated_name_containing_pic_is_not_mistaken_for_keyword():
    cobol = "01 REC.\n   05 CUST-PIC-CODE PIC X(5).\n"
    item = parse(cobol)[0].children[0]
    assert item.name == "CUST-PIC-CODE"
    assert item.pic.category == PicCategory.STRING
    assert item.pic.length == 5
