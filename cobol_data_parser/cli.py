from __future__ import annotations

import sys

import click

from . import __version__
from .emitter import to_json
from .parser import parse


@click.command()
@click.version_option(__version__, prog_name="cobol-data-parser")
@click.argument("input_file", type=click.Path(exists=True, allow_dash=True), default="-")
@click.option("-o", "--output", type=click.Path(), help="Output file (default: stdout)")
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
    indent: int,
    fixed: bool | None,
    copybook_dirs: tuple[str, ...],
) -> None:
    """Convert COBOL DATA DIVISION to JSON.

    Reads COBOL source from INPUT_FILE (or stdin with -) and writes a JSON
    representation of the data structure to stdout or --output.

    COPY statements are expanded when --copybook-dir is supplied.
    """
    try:
        if input_file == "-":
            text = sys.stdin.read()
        else:
            with open(input_file, encoding="utf-8") as f:
                text = f.read()

        items = parse(text, fixed_format=fixed, copybook_dirs=list(copybook_dirs) or None)
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
