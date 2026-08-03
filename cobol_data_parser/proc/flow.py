from __future__ import annotations

from dataclasses import dataclass, field

from .models import BranchCond, ProcedureDivision


@dataclass
class FlowEdge:
    """A single control-flow edge, with the branch (if any) it's nested
    under. `kind` is "PERFORM", "PERFORM-THRU" (one edge per paragraph in
    the expanded range), or "GO-TO"."""

    source: str
    target: str
    kind: str
    branch_path: list[BranchCond] = field(default_factory=list)


def build_flow_graph_detailed(proc: ProcedureDivision) -> list[FlowEdge]:
    """Build control-flow edges from PERFORM and GO TO statements, each
    tagged with the IF/EVALUATE branch (if any) it's nested under.

    PERFORM <a> THRU <b> expands to edges into every paragraph physically
    between <a> and <b> (inclusive), matching COBOL's THRU semantics; each
    expanded edge inherits the originating PERFORM's branch_path. GO TO
    edges represent an unconditional transfer rather than a call-and-return,
    but both are folded into the same edge list since this is a reachability
    graph, not a call stack model.
    """
    order = [p.name for p in proc.paragraphs]
    index = {name: i for i, name in enumerate(order)}

    edges: list[FlowEdge] = []
    for para in proc.paragraphs:
        for perform in para.performs:
            if perform.thru and perform.target in index and perform.thru in index:
                start, end = index[perform.target], index[perform.thru]
                if start > end:
                    start, end = end, start
                for target in order[start : end + 1]:
                    edges.append(FlowEdge(para.name, target, "PERFORM-THRU", perform.branch_path))
            else:
                edges.append(FlowEdge(para.name, perform.target, "PERFORM", perform.branch_path))
        for goto in para.go_tos:
            edges.append(FlowEdge(para.name, goto.target, "GO-TO", goto.branch_path))

    return edges


def build_flow_graph(proc: ProcedureDivision) -> list[tuple[str, str]]:
    """Build (caller_paragraph, target_paragraph) control-flow edges from
    PERFORM and GO TO statements — the branch-insensitive edge list; see
    build_flow_graph_detailed() for per-edge branch_path info."""
    return [(e.source, e.target) for e in build_flow_graph_detailed(proc)]
