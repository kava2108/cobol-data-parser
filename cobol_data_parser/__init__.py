"""cobol-data-parser: Convert COBOL DATA DIVISION to JSON, and decode COBOL records."""

from .codec import decode_record, iter_records
from .docgen import to_markdown_table
from .emitter import emit, to_json
from .models import DataItem, OccursClause, PicCategory, PicClause
from .parser import parse

__version__ = "0.4.0"
__all__ = [
    "parse",
    "emit",
    "to_json",
    "to_markdown_table",
    "decode_record",
    "iter_records",
    "DataItem",
    "PicClause",
    "PicCategory",
    "OccursClause",
]
