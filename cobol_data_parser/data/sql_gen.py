"""SQL DDL generation from a parsed DataItem tree.

Generates one CREATE TABLE per top-level (01/77) record, targeting the
shape of decode_record()'s decoded values (see schema_common.py) rather
than emit()'s JSON metadata shape.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import DataItem
from .schema_common import ValueField, ValueKind, build_value_fields, sql_identifier


def _scalar_sql_type(f: ValueField) -> str:
    if f.value_kind == ValueKind.STRING:
        length = f.length or f.byte_length or 1
        return f"VARCHAR({length})"

    if f.value_kind == ValueKind.INTEGER:
        digits = f.digits
        if digits is not None:
            if digits <= 9:
                return "INTEGER"
            if digits <= 18:
                return "BIGINT"
            return f"NUMERIC({digits})"
        byte_length = f.byte_length or 4
        if byte_length <= 2:
            return "SMALLINT"
        if byte_length <= 4:
            return "INTEGER"
        return "BIGINT"

    if f.value_kind == ValueKind.DECIMAL:
        precision = f.precision or 18
        scale = f.scale or 0
        return f"NUMERIC({precision},{scale})"

    if f.value_kind == ValueKind.FLOAT:
        byte_length = f.byte_length or 8
        return "FLOAT" if byte_length <= 4 else "DOUBLE PRECISION"

    raise AssertionError(f"unclassified value_kind for column {f.name!r}")


@dataclass
class _Column:
    name: str
    sql_type: str
    comment: str | None = None


@dataclass
class _Table:
    name: str
    columns: list[_Column]
    table_comment: str | None = None


def _child_table_name(parent_table: str, field_name: str) -> str:
    return sql_identifier(f"{parent_table}__{field_name}").upper()


def _occurs_comment(occurs) -> str:
    if occurs.is_variable:
        return f"OCCURS {occurs.min_occurs} TO {occurs.max_occurs} TIMES DEPENDING ON {occurs.depending_on}"
    return f"OCCURS {occurs.max_occurs} TIMES"


def _flatten_group(
    prefix: str,
    fields: list[ValueField],
    columns: list[_Column],
    tables: list[_Table],
    table_name: str,
) -> None:
    for f in fields:
        col_prefix = f"{prefix}_{f.name}" if prefix else f.name

        if f.occurs is not None:
            # OCCURS (fixed or ODO) -> a child table, one row per occurrence.
            # Nested OCCURS chains naturally: each level gets its own ID and
            # its own _PARENT_ID pointing at its immediate containing table,
            # rather than one flat FK back to the top-level record.
            child_name = _child_table_name(table_name, f.name)
            child_columns = [
                _Column("ID", "BIGINT", "synthetic primary key"),
                _Column("_PARENT_ID", "BIGINT", f"FK -> {table_name}.ID (placeholder, not enforced)"),
                _Column("_OCCURS_INDEX", "INTEGER", "0-based position within the OCCURS"),
            ]
            if f.is_group:
                _flatten_group("", f.children, child_columns, tables, child_name)
            else:
                child_columns.append(_Column(sql_identifier(f.name).upper(), _scalar_sql_type(f)))
            tables.append(_Table(child_name, child_columns, _occurs_comment(f.occurs)))

        elif f.is_group:
            _flatten_group(col_prefix, f.children, columns, tables, table_name)

        else:
            columns.append(_Column(sql_identifier(col_prefix).upper(), _scalar_sql_type(f)))


def _has_any_redefines(children: list[DataItem]) -> bool:
    for c in children:
        if c.redefines:
            return True
        if c.children and _has_any_redefines(c.children):
            return True
    return False


def _render_create_table(table: _Table) -> str:
    lines = []
    if table.table_comment:
        lines.append(f"-- {table.table_comment}")
    lines.append(f"CREATE TABLE {table.name} (")
    last = len(table.columns) - 1
    for i, c in enumerate(table.columns):
        suffix = "," if i < last else ""
        line = f"  {c.name} {c.sql_type}{suffix}"
        if c.comment:
            line += f"  -- {c.comment}"
        lines.append(line)
    lines.append(");")
    return "\n".join(lines)


def to_sql_ddl(items: list[DataItem]) -> str:
    """Generate CREATE TABLE DDL for each top-level 01/77 record with
    children, mirroring decode_record()'s decoded-value shape.

    REDEFINES: the base field and every alias become separate nullable
    columns covering the same physical bytes (matching decode_record(),
    which decodes both independently rather than choosing one) — only one
    is meaningful per row; the table gets a comment noting this, since SQL
    has no way to express "exactly one of these columns is valid" as a
    constraint here.

    OCCURS (fixed or OCCURS...DEPENDING ON): becomes a child table named
    <TABLE>__<FIELD> with a synthetic ID primary key, a _PARENT_ID
    placeholder FK to the containing table's ID (not enforced — wire it to
    your actual key), and an _OCCURS_INDEX column.

    FILLER and level-88 items are excluded, matching emit(). Only
    single-target (non-THRU) level-66 RENAMES are included, as a duplicate
    column of their target — matching decode_record().
    """
    statements: list[str] = []

    for item in items:
        if not item.is_group:
            continue

        table_name = sql_identifier(item.name).upper()
        columns: list[_Column] = [_Column("ID", "BIGINT", "synthetic primary key")]
        tables: list[_Table] = []
        _flatten_group("", build_value_fields(item.children), columns, tables, table_name)

        table_comment = None
        if _has_any_redefines(item.children):
            table_comment = (
                "One or more fields are REDEFINES siblings covering the same bytes; "
                "only one is meaningful per row."
            )

        statements.append(_render_create_table(_Table(table_name, columns, table_comment)))
        for child_table in tables:
            statements.append(_render_create_table(child_table))

    return "\n\n".join(statements)
