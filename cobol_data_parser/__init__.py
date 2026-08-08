"""cobol-data-parser: Convert COBOL DATA DIVISION to JSON, and decode COBOL records."""

from .data.codec import decode_record, encode_record, iter_records
from .data.docgen import to_markdown_table
from .data.emitter import emit, to_json
from .data.models import DataItem, OccursClause, PicCategory, PicClause
from .data.openapi_gen import to_openapi_json, to_openapi_schema
from .data.parser import parse
from .data.sql_gen import to_sql_ddl
from .data.ts_gen import to_typescript

__version__ = "0.9.0"
__all__ = [
    "parse",
    "emit",
    "to_json",
    "to_markdown_table",
    "to_sql_ddl",
    "to_typescript",
    "to_openapi_schema",
    "to_openapi_json",
    "decode_record",
    "encode_record",
    "iter_records",
    "DataItem",
    "PicClause",
    "PicCategory",
    "OccursClause",
]
