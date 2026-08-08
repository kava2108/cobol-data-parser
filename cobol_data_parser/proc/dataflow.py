"""Per-paragraph data-item read/write facts, derived from MOVE/ADD/SUBTRACT/
MULTIPLY/DIVIDE/COMPUTE/ACCEPT/DISPLAY statements (see models.py) -- the
deterministic ground truth consumed by docgen.py's to_markdown_ipo().

Figurative constants (ZERO, SPACES, HIGH-VALUES, ...) are indistinguishable
from real data-item identifiers by this regex-based tool, so they show up as
spurious READ facts; quoted literals are excluded since they're
unambiguous, and bare numeric tokens (from a COMPUTE's unparsed expression)
are excluded too.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import BranchCond, ProcedureDivision


@dataclass
class DataFlowFact:
    """One paragraph's read or write of one data item, from a single
    statement instance. `stmt_kind` is one of "MOVE", "ADD", "SUBTRACT",
    "MULTIPLY", "DIVIDE", "COMPUTE", "ACCEPT", "DISPLAY"."""

    paragraph: str
    item: str
    access: str
    stmt_kind: str
    branch_path: list[BranchCond] = field(default_factory=list)


def _is_literal(token: str) -> bool:
    return token.startswith("'") or token.startswith('"')


def build_dataflow_facts(proc: ProcedureDivision) -> list[DataFlowFact]:
    """Build per-statement READ/WRITE DataFlowFacts for every paragraph."""
    facts: list[DataFlowFact] = []

    for para in proc.paragraphs:
        for mv in para.moves:
            if not _is_literal(mv.source):
                facts.append(DataFlowFact(para.name, mv.source, "READ", "MOVE", mv.branch_path))
            for target in mv.targets:
                facts.append(DataFlowFact(para.name, target, "WRITE", "MOVE", mv.branch_path))

        for stmt in para.arithmetic:
            for operand in stmt.operands:
                if not _is_literal(operand) and not operand.isdigit():
                    facts.append(DataFlowFact(para.name, operand, "READ", stmt.operation, stmt.branch_path))
            for target in stmt.targets:
                facts.append(DataFlowFact(para.name, target, "WRITE", stmt.operation, stmt.branch_path))

        for stmt in para.accepts:
            facts.append(DataFlowFact(para.name, stmt.target, "WRITE", "ACCEPT", stmt.branch_path))

        for stmt in para.displays:
            for item in stmt.items:
                if not _is_literal(item):
                    facts.append(DataFlowFact(para.name, item, "READ", "DISPLAY", stmt.branch_path))

    return facts
