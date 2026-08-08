"""Program specification document generation (Markdown) for PROCEDURE DIVISION.

Renders the parsed ProcedureDivision — sections, paragraphs, and their
PERFORM/CALL/GO TO statements — plus the derived control-flow and CALL
graphs, as a structural spec document (`to_markdown_spec()`), or as a
natural-language IPO (Input-Process-Output) document built from MOVE/ADD/
SUBTRACT/MULTIPLY/DIVIDE/COMPUTE/ACCEPT/DISPLAY read/write facts
(`to_markdown_ipo()`).

Statements inside IF/ELSE or EVALUATE/WHEN blocks (using explicit END-IF/
END-EVALUATE scope terminators) are annotated with their branch condition;
see parser.py's docstring for the full scope of what's recognized.
"""
from __future__ import annotations

from .dataflow import DataFlowFact, build_dataflow_facts
from .depgraph import build_call_graph
from .fileaccess import build_file_access_graph
from .flow import build_flow_graph
from .models import (
    AcceptStmt,
    ArithmeticStmt,
    BranchCond,
    CallStmt,
    DisplayStmt,
    FileDescriptor,
    GoToStmt,
    MoveStmt,
    PerformStmt,
    ProcedureDivision,
)


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


_ARITH_TEMPLATES = {
    "ADD": "{operands} を {targets} に加算する",
    "SUBTRACT": "{targets} から {operands} を減算する",
    "MULTIPLY": "{targets} に {operands} を乗算する",
    "DIVIDE": "{targets} を {operands} で除算する",
    "COMPUTE": "{operands} から {targets} を算出する",
}


def _finish(sentence: str, branch_path: list[BranchCond]) -> str:
    return sentence + _branch_suffix(branch_path) + "。"


def _move_sentence(stmt: MoveStmt) -> str:
    particle = "の対応項目を" if stmt.corresponding else "を"
    targets = "、".join(stmt.targets) or "(不明)"
    return _finish(f"{stmt.source} {particle} {targets} に転記する", stmt.branch_path)


def _arithmetic_sentence(stmt: ArithmeticStmt) -> str:
    operands = "、".join(stmt.operands) or "(不明)"
    targets = "、".join(stmt.targets) or "(不明)"
    return _finish(_ARITH_TEMPLATES[stmt.operation].format(operands=operands, targets=targets), stmt.branch_path)


def _accept_sentence(stmt: AcceptStmt) -> str:
    src = f"（{stmt.from_source} から）" if stmt.from_source else ""
    return _finish(f"{stmt.target} を受け取る{src}", stmt.branch_path)


def _display_sentence(stmt: DisplayStmt) -> str:
    return _finish(f"{'、'.join(stmt.items)} を表示する", stmt.branch_path)


def _unique_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def to_markdown_ipo(proc: ProcedureDivision, render: str = "template") -> str:
    """Render a natural-language IPO (Input-Process-Output) specification
    document (Markdown), one section per paragraph that has at least one
    MOVE/ADD/SUBTRACT/MULTIPLY/DIVIDE/COMPUTE/ACCEPT/DISPLAY statement.

    Control flow (PERFORM/CALL/GO TO) and file access are already covered by
    to_markdown_spec()'s own sections and aren't repeated here.

    `render="template"` (default) renders mechanical Japanese sentences with
    no external dependency. `render="llm"` sends each paragraph's
    already-extracted facts (never raw COBOL source) to an LLM to phrase the
    "処理" section as prose instead — see llm_nlg.py; this needs the
    `llm` extra installed. Either way, the "入力"/"出力" lists themselves
    are always the deterministic dataflow.py facts, never LLM output.
    """
    if render not in ("template", "llm"):
        raise ValueError(f"unknown render mode: {render!r}")

    facts_by_para: dict[str, list[DataFlowFact]] = {}
    for fact in build_dataflow_facts(proc):
        facts_by_para.setdefault(fact.paragraph, []).append(fact)

    lines: list[str] = [f"# IPO仕様書: {proc.program_id or '(不明)'}", ""]

    for para in proc.paragraphs:
        para_facts = facts_by_para.get(para.name, [])
        inputs = _unique_ordered([f.item for f in para_facts if f.access == "READ"])
        outputs = _unique_ordered([f.item for f in para_facts if f.access == "WRITE"])

        sentences: list[str] = (
            [_move_sentence(s) for s in para.moves]
            + [_arithmetic_sentence(s) for s in para.arithmetic]
            + [_accept_sentence(s) for s in para.accepts]
            + [_display_sentence(s) for s in para.displays]
        )

        if not sentences:
            continue

        lines += [f"## {para.name}", ""]
        lines.append(f"**入力**: {'、'.join(inputs) if inputs else '(なし)'}")
        lines.append("")

        if render == "llm":
            from .llm_nlg import render_paragraph_narrative

            narrative = render_paragraph_narrative(para.name, inputs, outputs, sentences)
            lines += ["**処理**:", "", narrative, ""]
        else:
            lines.append("**処理**:")
            lines += [f"- {s}" for s in sentences]
            lines.append("")

        lines.append(f"**出力**: {'、'.join(outputs) if outputs else '(なし)'}")
        lines.append("")

    return "\n".join(lines)
