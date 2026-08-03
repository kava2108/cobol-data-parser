from __future__ import annotations

import sys

import click

from . import __version__
from .data.docgen import to_markdown_table
from .data.emitter import to_json
from .data.openapi_gen import to_openapi_json
from .data.parser import parse
from .data.sql_gen import to_sql_ddl
from .data.ts_gen import to_typescript
from .proc.docgen import to_markdown_spec
from .proc.emitter import to_dot, to_json as to_proc_json, to_python, to_sql
from .proc.parser import parse as parse_proc


@click.command()
@click.version_option(__version__, prog_name="cobol-data-parser")
@click.argument("input_file", type=click.Path(exists=True, allow_dash=True), default="-")
@click.option("-o", "--output", type=click.Path(), help="Output file (default: stdout)")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "markdown", "sql-ddl", "typescript", "openapi"]),
    default="json",
    show_default=True,
    help=(
        "Output format: JSON schema, a Markdown data-item definition table, "
        "SQL CREATE TABLE DDL, TypeScript interfaces, or an OpenAPI components/schemas "
        "document — the last three mirror decode_record()'s decoded-value shape, not "
        "the JSON schema's metadata shape"
    ),
)
@click.option("--indent", type=int, default=2, show_default=True, help="JSON indentation spaces")
@click.option(
    "--fixed/--free",
    default=None,
    help="Force fixed-format (cols 1-72) or free-format parsing",
)
@click.option(
    "--copybook-dir",
    "copybook_dirs",
    multiple=True,
    type=click.Path(exists=True, file_okay=False),
    help="Directory to search for copybooks (repeatable)",
)
def main(
    input_file: str,
    output: str | None,
    output_format: str,
    indent: int,
    fixed: bool | None,
    copybook_dirs: tuple[str, ...],
) -> None:
    """Convert COBOL DATA DIVISION to JSON (or a Markdown definition table).

    Reads COBOL source from INPUT_FILE (or stdin with -) and writes a JSON
    representation of the data structure to stdout or --output. Pass
    --format markdown for a human-readable data-item definition table instead.

    COPY statements are expanded when --copybook-dir is supplied.
    """
    try:
        if input_file == "-":
            text = sys.stdin.read()
        else:
            with open(input_file, encoding="utf-8") as f:
                text = f.read()

        items = parse(text, fixed_format=fixed, copybook_dirs=list(copybook_dirs) or None)
        if output_format == "markdown":
            result = to_markdown_table(items)
        elif output_format == "sql-ddl":
            result = to_sql_ddl(items)
        elif output_format == "typescript":
            result = to_typescript(items)
        elif output_format == "openapi":
            result = to_openapi_json(items, indent=indent)
        else:
            result = to_json(items, indent=indent)

        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(result)
                f.write("\n")
        else:
            click.echo(result)

    except Exception as exc:  # noqa: BLE001
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@click.command()
@click.version_option(__version__, prog_name="cobol-proc-parser")
@click.argument("input_file", type=click.Path(exists=True, allow_dash=True), default="-")
@click.option("-o", "--output", type=click.Path(), help="Output file (default: stdout)")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "dot", "sql", "python", "spec"]),
    default="json",
    show_default=True,
    help=(
        "Output format: JSON schema, Graphviz DOT, SQL INSERT statements, "
        "Python pretty-print, or a Markdown program specification document"
    ),
)
@click.option(
    "--graph",
    type=click.Choice(["flow", "call", "file"]),
    default="flow",
    show_default=True,
    help="Which graph to emit for --format dot/sql: PERFORM control-flow, CALL dependencies, or file access",
)
@click.option("--indent", type=int, default=2, show_default=True, help="JSON indentation spaces")
@click.option(
    "--fixed/--free",
    default=None,
    help="Force fixed-format (cols 1-72) or free-format parsing",
)
@click.option(
    "--copybook-dir",
    "copybook_dirs",
    multiple=True,
    type=click.Path(exists=True, file_okay=False),
    help="Directory to search for copybooks referenced by FILE SECTION FD entries (repeatable)",
)
def proc_main(
    input_file: str,
    output: str | None,
    output_format: str,
    graph: str,
    indent: int,
    fixed: bool | None,
    copybook_dirs: tuple[str, ...],
) -> None:
    """Analyze COBOL PROCEDURE DIVISION: PERFORM control-flow, CALL dependency, and file access graphs.

    Reads COBOL source from INPUT_FILE (or stdin with -) and writes the
    requested representation to stdout or --output. Only the most common
    forms of PERFORM, SECTION, CALL, and READ/WRITE/REWRITE/DELETE/START
    statements are recognized.
    """
    try:
        if input_file == "-":
            text = sys.stdin.read()
        else:
            with open(input_file, encoding="utf-8") as f:
                text = f.read()

        proc = parse_proc(text, fixed_format=fixed, copybook_dirs=list(copybook_dirs) or None)

        if output_format == "json":
            result = to_proc_json(proc, indent=indent)
        elif output_format == "dot":
            result = to_dot(proc, graph=graph)
        elif output_format == "sql":
            result = to_sql(proc, graph=graph)
        elif output_format == "spec":
            result = to_markdown_spec(proc)
        else:
            result = to_python(proc)

        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(result)
                f.write("\n")
        else:
            click.echo(result)

    except Exception as exc:  # noqa: BLE001
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
