"""Tests for PIC/USAGE type lowering -> physical byte length."""
from __future__ import annotations

import pytest

from cobol_data_parser.pic_parser import parse_pic
from cobol_data_parser.storage import compute_byte_length


@pytest.mark.parametrize(
    "pic_str, usage, expected_bytes",
    [
        ("X(10)", None, 10),
        ("9(5)", None, 5),  # DISPLAY numeric: 1 byte/digit, sign over-punched
        ("S9(5)", None, 5),
        ("S9(7)V99", None, 9),  # DISPLAY decimal: precision + scale
        ("9(4)", "COMP", 2),  # 1-4 digits -> 2 bytes
        ("9(5)", "COMP", 4),  # 5-9 digits -> 4 bytes
        ("9(9)", "COMP", 4),
        ("9(10)", "COMP", 8),  # 10-18 digits -> 8 bytes
        ("9(4)", "BINARY", 2),
        ("9(9)", "COMP-5", 4),
        ("S9(9)V99", "COMP-3", 6),  # floor(11/2) + 1
        ("S999V99", "PACKED-DECIMAL", 3),  # floor(5/2) + 1
        ("9(3)", "COMP-3", 2),  # floor(3/2) + 1
    ],
)
def test_compute_byte_length_from_pic(pic_str, usage, expected_bytes):
    pic = parse_pic(pic_str)
    assert compute_byte_length(pic, usage) == expected_bytes


@pytest.mark.parametrize(
    "usage, expected_bytes",
    [
        ("COMP-1", 4),
        ("COMP-2", 8),
        ("INDEX", 4),
        ("POINTER", 4),
    ],
)
def test_fixed_length_usages_without_pic(usage, expected_bytes):
    assert compute_byte_length(None, usage) == expected_bytes


def test_no_pic_and_unknown_usage_returns_none():
    assert compute_byte_length(None, None) is None
