"""Program specification document generation (Markdown) for PROCEDURE DIVISION.

Renders the parsed ProcedureDivision — sections, paragraphs, and their
PERFORM/CALL/GO TO statements — plus the derived control-flow and CALL
graphs, as a structural spec document.

This is a structural summary, not a natural-language IPO (Input-Process-
Output) narrative: the parser doesn't track which data items each statement
reads or writes, and statements inside IF/EVALUATE branches are listed
without their branch condition (see parser.py's docstring for the full
scope of what's recognized).
"""
from __future__ import annotations

from .depgraph import build_call_graph
from .flow import build_flow_graph
from .models import CallStmt, PerformStmt, ProcedureDivision


def _perform_cell(stmt: PerformStmt) -> str:
    parts = [stmt.target]
    if stmt.thru:
        parts.append(f"THRU {stmt.thru}")
    if stmt.varying:
        parts.append(f"VARYING {stmt.varying}")
    if stmt.until:
        parts.append("UNTIL ...")
    return " ".join(parts)


def _call_cell(stmt: CallStmt) -> str:
    label = f"'{stmt.target}'" if not stmt.dynamic else f"{stmt.target}（動的）"
    extras = []
    if stmt.using:
        extras.append("USING " + ", ".join(stmt.using))
    if stmt.returning:
        extras.append(f"RETURNING {stmt.returning}")
    return f"{label} — {' / '.join(extras)}" if extras else label


def to_markdown_spec(proc: ProcedureDivision) -> str:
    """Render a structural program specification document (Markdown)."""
    lines: list[str] = [f"# プログラム仕様書: {proc.program_id or '(不明)'}", ""]

    if proc.sections:
        lines += [f"**SECTION**: {', '.join(proc.sections)}", ""]

    lines += ["## 段落一覧", "", "| 段落 | SECTION | PERFORM | CALL | GO TO |", "|---|---|---|---|---|"]
    for p in proc.paragraphs:
        performs = "<br>".join(_perform_cell(s) for s in p.performs)
        calls = "<br>".join(_call_cell(s) for s in p.calls)
        gotos = "<br>".join(g.target for g in p.go_tos)
        lines.append(f"| {p.name} | {p.section or ''} | {performs} | {calls} | {gotos} |")
    lines.append("")

    lines += ["## 制御フロー（PERFORM / GO TO）", ""]
    flow_edges = build_flow_graph(proc)
    lines += [f"- {source} → {target}" for source, target in flow_edges] or ["(なし)"]
    lines.append("")

    lines += ["## 外部依存（CALL）", ""]
    call_edges = build_call_graph(proc)
    lines += [f"- {source} → {target}" for source, target in call_edges] or ["(なし)"]
    lines.append("")

    return "\n".join(lines)
