"""Tests for the SQL DDL / TypeScript / OpenAPI schema generators.

These generators target decode_record()'s decoded-value shape, not
emit()'s JSON metadata shape — see cobol_data_parser/data/schema_common.py.
"""
from __future__ import annotations

from cobol_data_parser.data.openapi_gen import to_openapi_schema
from cobol_data_parser.data.parser import parse
from cobol_data_parser.data.schema_common import ValueKind, classify_value_kind, pascal_case, sql_identifier
from cobol_data_parser.data.sql_gen import to_sql_ddl
from cobol_data_parser.data.ts_gen import to_typescript

BASIC = """
01 CUSTOMER-REC.
   05 CUST-ID        PIC 9(5).
   05 CUST-NAME.
      10 FIRST-NAME  PIC X(10).
      10 LAST-NAME   PIC X(10).
   05 BALANCE        PIC S9(7)V99.
"""


def test_value_kind_classification_for_each_pic_category():
    cobol = """
    01 REC.
       05 A PIC X(10).
       05 B PIC 9(5).
       05 C PIC S9(7)V99.
       05 D PIC S9(9) COMP.
       05 E PIC S9(9)V99 COMP-3.
       05 F PIC S9(9) COMP-3.
       05 G PIC S9(5)V99 COMP-1.
    """
    items = parse(cobol)[0].children
    by_name = {i.name: i for i in items}
    assert classify_value_kind(by_name["A"]) == ValueKind.STRING
    assert classify_value_kind(by_name["B"]) == ValueKind.INTEGER
    assert classify_value_kind(by_name["C"]) == ValueKind.DECIMAL
    assert classify_value_kind(by_name["D"]) == ValueKind.INTEGER
    assert classify_value_kind(by_name["E"]) == ValueKind.DECIMAL
    # PACKED-DECIMAL with no V (no fractional part) decodes to a plain int,
    # not Decimal — see codec.py's _apply_scale.
    assert classify_value_kind(by_name["F"]) == ValueKind.INTEGER
    assert classify_value_kind(by_name["G"]) == ValueKind.FLOAT


def test_naming_helpers():
    assert sql_identifier("CUST-ID") == "CUST_ID"
    assert pascal_case("CUSTOMER-REC") == "CustomerRec"


def test_sql_ddl_basic_table_and_flattened_group():
    ddl = to_sql_ddl(parse(BASIC))
    assert "CREATE TABLE CUSTOMER_REC (" in ddl
    assert "CUST_ID INTEGER" in ddl
    assert "CUST_NAME_FIRST_NAME VARCHAR(10)" in ddl
    assert "CUST_NAME_LAST_NAME VARCHAR(10)" in ddl
    assert "BALANCE NUMERIC(7,2)" in ddl


def test_sql_ddl_redefines_are_sibling_columns_with_comment():
    cobol = """
    01 REC.
       05 AMOUNT-DISPLAY PIC X(8).
       05 AMOUNT-PACKED  REDEFINES AMOUNT-DISPLAY PIC S9(9)V99 COMP-3.
    """
    ddl = to_sql_ddl(parse(cobol))
    assert "AMOUNT_DISPLAY VARCHAR(8)" in ddl
    assert "AMOUNT_PACKED NUMERIC(9,2)" in ddl
    assert "REDEFINES siblings" in ddl


def test_sql_ddl_occurs_becomes_child_table():
    cobol = """
    01 REC.
       05 ITEM-COUNT PIC 9(3).
       05 ITEMS OCCURS 1 TO 10 TIMES DEPENDING ON ITEM-COUNT.
          10 ITEM-ID  PIC 9(5).
          10 ITEM-AMT PIC S9(7)V99 COMP-3.
    """
    ddl = to_sql_ddl(parse(cobol))
    statements = ddl.split("\n\n")
    assert "CREATE TABLE REC (" in statements[0]
    assert "ITEM_COUNT" in statements[0]
    assert "ITEMS" not in statements[0]
    assert "CREATE TABLE REC__ITEMS (" in ddl
    assert "_PARENT_ID BIGINT" in ddl
    assert "_OCCURS_INDEX INTEGER" in ddl
    assert "ITEM_ID INTEGER" in ddl
    assert "ITEM_AMT NUMERIC(7,2)" in ddl
    assert "DEPENDING ON ITEM-COUNT" in ddl


def test_sql_ddl_excludes_filler_and_level_88():
    cobol = """
    01 REC.
       05 FLAG PIC X(1).
          88 FLAG-YES VALUE 'Y'.
       05 FILLER PIC X(3).
    """
    ddl = to_sql_ddl(parse(cobol))
    assert "FLAG" in ddl
    assert "FLAG_YES" not in ddl
    assert "FILLER" not in ddl


def test_sql_ddl_includes_single_target_renames_but_not_thru():
    cobol = """
    01 REC.
       05 FIELD-A PIC X(5).
       05 FIELD-B PIC 9(3).
       66 ALIAS-A  RENAMES FIELD-A.
       66 COMBINED RENAMES FIELD-A THRU FIELD-B.
    """
    ddl = to_sql_ddl(parse(cobol))
    assert "ALIAS_A VARCHAR(5)" in ddl
    assert "COMBINED" not in ddl


def test_typescript_basic_interface():
    ts = to_typescript(parse(BASIC))
    assert "export interface CustomerRec {" in ts
    assert '"CUST-ID": number;' in ts
    assert '"FIRST-NAME": string;' in ts
    assert '"BALANCE": string;' in ts
    assert "floating-point precision loss" in ts


def test_typescript_occurs_becomes_array():
    cobol = """
    01 REC.
       05 ITEMS OCCURS 5 TIMES.
          10 ITEM-ID PIC 9(5).
    """
    ts = to_typescript(parse(cobol))
    assert '"ITEMS": Array<{' in ts
    assert '"ITEM-ID": number;' in ts


def test_openapi_schema_structure_and_array_bounds():
    cobol = """
    01 REC.
       05 ITEM-COUNT PIC 9(3).
       05 ITEMS OCCURS 1 TO 5 TIMES DEPENDING ON ITEM-COUNT.
          10 ITEM-ID PIC 9(5).
    """
    schema = to_openapi_schema(parse(cobol))
    rec = schema["components"]["schemas"]["Rec"]
    assert rec["type"] == "object"
    assert rec["properties"]["ITEM-COUNT"] == {"type": "integer"}
    items_schema = rec["properties"]["ITEMS"]
    assert items_schema["type"] == "array"
    assert items_schema["minItems"] == 1
    assert items_schema["maxItems"] == 5
    assert items_schema["items"]["properties"]["ITEM-ID"] == {"type": "integer"}


def test_openapi_decimal_field_is_string_with_description():
    schema = to_openapi_schema(parse(BASIC))
    balance = schema["components"]["schemas"]["CustomerRec"]["properties"]["BALANCE"]
    assert balance["type"] == "string"
    assert "description" in balance
