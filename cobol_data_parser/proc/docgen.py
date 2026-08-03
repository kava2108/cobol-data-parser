"""Program specification document generation (Markdown) for PROCEDURE DIVISION.

Renders the parsed ProcedureDivision — sections, paragraphs, and their
PERFORM/CALL/GO TO statements — plus the derived control-flow and CALL
graphs, as a structural spec document.

This is a structural summary, not a natural-language IPO (Input-Process-
Output) narrative: the parser doesn't track which data items each statement
reads or writes. Statements inside IF/ELSE or EVALUATE/WHEN blocks (using
explicit END-IF/END-EVALUATE scope terminators) are annotated with their
branch condition; see parser.py's docstring for the full scope of what's
recognized.
"""
from __future__ import annotations

from .depgraph import build_call_graph
from .fileaccess import build_file_access_graph
from .flow import build_flow_graph
from .models import BranchCond, CallStmt, FileDescriptor, GoToStmt, PerformStmt, ProcedureDivision


def _branch_suffix(branch_path: list[BranchCond]) -> str:
    if not branch_path:
        return ""
    label = " / ".join(f"{b.kind}: {b.text}" for b in branch_path)
    return f" [{label}]"


def _file_descriptor_cell(fd: FileDescriptor) -> tuple[str, str, str, str]:
    keys = [fd.record_key] if fd.record_key else []
    keys += fd.alternate_record_keys
    return (fd.name, fd.organization or "", fd.access_mode or "", ", ".join(keys))


def _perform_cell(stmt: PerformStmt) -> str:
    parts = [stmt.target]
    if stmt.thru:
        parts.append(f"THRU {stmt.thru}")
    if stmt.varying:
        parts.append(f"VARYING {stmt.varying}")
    if stmt.until:
        parts.append("UNTIL ...")
    return " ".join(parts) + _branch_suffix(stmt.branch_path)


def _call_cell(stmt: CallStmt) -> str:
    label = f"'{stmt.target}'" if not stmt.dynamic else f"{stmt.target}（動的）"
    extras = []
    if stmt.using:
        extras.append("USING " + ", ".join(stmt.using))
    if stmt.returning:
        extras.append(f"RETURNING {stmt.returning}")
    cell = f"{label} — {' / '.join(extras)}" if extras else label
    return cell + _branch_suffix(stmt.branch_path)


def _goto_cell(stmt: GoToStmt) -> str:
    return stmt.target + _branch_suffix(stmt.branch_path)


def to_markdown_spec(proc: ProcedureDivision) -> str:
    """Render a structural program specification document (Markdown)."""
    lines: list[str] = [f"# プログラム仕様書: {proc.program_id or '(不明)'}", ""]

    if proc.sections:
        lines += [f"**SECTION**: {', '.join(proc.sections)}", ""]

    lines += ["## 段落一覧", "", "| 段落 | SECTION | PERFORM | CALL | GO TO |", "|---|---|---|---|---|"]
    for p in proc.paragraphs:
        performs = "<br>".join(_perform_cell(s) for s in p.performs)
        calls = "<br>".join(_call_cell(s) for s in p.calls)
        gotos = "<br>".join(_goto_cell(g) for g in p.go_tos)
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

    lines += ["## ファイルアクセス", ""]
    if proc.files:
        lines += ["| ファイル名 | ORGANIZATION | ACCESS MODE | キー |", "|---|---|---|---|"]
        for fd in proc.files:
            name, org, access, keys = _file_descriptor_cell(fd)
            lines.append(f"| {name} | {org} | {access} | {keys} |")
        lines.append("")

    file_edges = build_file_access_graph(proc)
    if file_edges:
        lines += ["| 段落 | 操作 | ファイル | 分岐 |", "|---|---|---|---|"]
        for e in file_edges:
            branch = _branch_suffix(e.branch_path).strip(" []")
            lines.append(f"| {e.paragraph} | {e.operation} | {e.file_name} | {branch} |")
        lines.append("")
    elif not proc.files:
        lines.append("(なし)")
        lines.append("")

    return "\n".join(lines)
