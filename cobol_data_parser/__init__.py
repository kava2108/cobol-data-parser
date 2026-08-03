"""cobol-data-parser: Convert COBOL DATA DIVISION to JSON, and decode COBOL records."""

from .data.codec import decode_record, iter_records
from .data.docgen import to_markdown_table
from .data.emitter import emit, to_json
from .data.models import DataItem, OccursClause, PicCategory, PicClause
from .data.parser import parse

__version__ = "0.5.0"
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
