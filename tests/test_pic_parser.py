import pytest

from cobol_data_parser.data.models import PicCategory
from cobol_data_parser.data.pic_parser import parse_pic


@pytest.mark.parametrize(
    "pic, expected_cat, expected_len",
    [
        ("X(10)", PicCategory.STRING, 10),
        ("XXX", PicCategory.STRING, 3),
        ("X(1)", PicCategory.STRING, 1),
        ("9(5)", PicCategory.NUMERIC, 5),
        ("999", PicCategory.NUMERIC, 3),
        ("S9(5)", PicCategory.SIGNED_NUMERIC, 5),
        ("S999", PicCategory.SIGNED_NUMERIC, 3),
        ("A(10)", PicCategory.ALPHABETIC, 10),
        ("AAA", PicCategory.ALPHABETIC, 3),
    ],
)
def test_simple_types(pic, expected_cat, expected_len):
    p = parse_pic(pic)
    assert p.category == expected_cat
    assert p.length == expected_len
    assert p.raw == pic


@pytest.mark.parametrize(
    "pic, expected_cat, precision, scale",
    [
        ("9(7)V99", PicCategory.DECIMAL, 7, 2),
        ("9(7)V9(2)", PicCategory.DECIMAL, 7, 2),
        ("S9(7)V99", PicCategory.SIGNED_DECIMAL, 7, 2),
        ("S9(7)V9(2)", PicCategory.SIGNED_DECIMAL, 7, 2),
        ("S999V99", PicCategory.SIGNED_DECIMAL, 3, 2),
        ("9V9", PicCategory.DECIMAL, 1, 1),
    ],
)
def test_decimal_types(pic, expected_cat, precision, scale):
    p = parse_pic(pic)
    assert p.category == expected_cat
    assert p.precision == precision
    assert p.scale == scale
    assert p.length is None


def test_raw_preserved():
    p = parse_pic("S9(7)V99")
    assert p.raw == "S9(7)V99"


def test_mixed_falls_back_to_edited():
    p = parse_pic("X9")
    assert p.category == PicCategory.ALPHANUMERIC_EDITED


@pytest.mark.parametrize(
    "pic, expected_cat, expected_len, expected_symbols",
    [
        ("ZZZ,ZZ9.99", PicCategory.NUMERIC_EDITED, 10, ["Z", ",", "."]),
        ("9,999", PicCategory.NUMERIC_EDITED, 5, [","]),
        ("999-", PicCategory.NUMERIC_EDITED, 4, ["-"]),
        ("999CR", PicCategory.NUMERIC_EDITED, 5, ["CR"]),
        ("999DB", PicCategory.NUMERIC_EDITED, 5, ["DB"]),
        ("***,**9", PicCategory.NUMERIC_EDITED, 7, ["*", ","]),
        ("$$$,$$9.99", PicCategory.NUMERIC_EDITED, 10, ["$", ",", "."]),
        ("BB999", PicCategory.NUMERIC_EDITED, 5, ["B"]),
        ("999/99/99", PicCategory.NUMERIC_EDITED, 9, ["/"]),
        ("XX0XX", PicCategory.ALPHANUMERIC_EDITED, 5, ["0"]),
    ],
)
def test_edited_pictures_capture_symbols_and_width(pic, expected_cat, expected_len, expected_symbols):
    p = parse_pic(pic)
    assert p.category == expected_cat
    assert p.length == expected_len
    assert p.edit_symbols == expected_symbols


def test_edit_symbol_alone_forces_numeric_edited():
    """A pure-9 PIC with only insertion symbols (no Z/*) must not be
    misclassified as plain NUMERIC — the comma makes it edited."""
    p = parse_pic("9(3),999")
    assert p.category == PicCategory.NUMERIC_EDITED
    assert p.length == 7
    assert p.edit_symbols == [","]
