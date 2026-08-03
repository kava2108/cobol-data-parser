from __future__ import annotations

import json
from pprint import pformat

from .depgraph import build_call_graph
from .flow import build_flow_graph, build_flow_graph_detailed
from .models import BranchCond, ProcedureDivision

_GRAPH_BUILDERS = {"flow": build_flow_graph, "call": build_call_graph}


def _branch_path_json(branch_path: list[BranchCond]) -> list[dict]:
    return [{"kind": b.kind, "text": b.text} for b in branch_path]


def _to_dict(proc: ProcedureDivision) -> dict:
    def _perform(s):
        node = {"target": s.target, "thru": s.thru, "varying": s.varying, "until": s.until}
        if s.branch_path:
            node["branch_path"] = _branch_path_json(s.branch_path)
        return node

    def _call(c):
        node = {"target": c.target, "dynamic": c.dynamic, "using": c.using, "returning": c.returning}
        if c.branch_path:
            node["branch_path"] = _branch_path_json(c.branch_path)
        return node

    def _goto(g):
        node = {"target": g.target}
        if g.branch_path:
            node["branch_path"] = _branch_path_json(g.branch_path)
        return node

    return {
        "program_id": proc.program_id,
        "sections": proc.sections,
        "paragraphs": [
            {
                "name": p.name,
                "section": p.section,
                "performs": [_perform(s) for s in p.performs],
                "calls": [_call(c) for c in p.calls],
                "go_tos": [_goto(g) for g in p.go_tos],
            }
            for p in proc.paragraphs
        ],
        "flow_edges": build_flow_graph(proc),
        "call_edges": build_call_graph(proc),
    }


def to_json(proc: ProcedureDivision, indent: int = 2) -> str:
    return json.dumps(_to_dict(proc), indent=indent, ensure_ascii=False)


def to_python(proc: ProcedureDivision) -> str:
    return pformat(_to_dict(proc))


def _edges(proc: ProcedureDivision, graph: str) -> list[tuple[str, str]]:
    if graph not in _GRAPH_BUILDERS:
        raise ValueError(f"Unknown graph {graph!r}; expected 'flow' or 'call'")
    return _GRAPH_BUILDERS[graph](proc)


def _branch_label(branch_path: list[BranchCond]) -> str | None:
    if not branch_path:
        return None
    return " / ".join(f"{b.kind}: {b.text}" for b in branch_path)


def to_dot(proc: ProcedureDivision, graph: str = "flow") -> str:
    if graph not in _GRAPH_BUILDERS:
        raise ValueError(f"Unknown graph {graph!r}; expected 'flow' or 'call'")

    lines = [f"digraph {graph} {{"]
    if graph == "flow":
        for edge in build_flow_graph_detailed(proc):
            label = _branch_label(edge.branch_path)
            if label:
                escaped = label.replace('"', '\\"')
                lines.append(f'  "{edge.source}" -> "{edge.target}" [label="{escaped}"];')
            else:
                lines.append(f'  "{edge.source}" -> "{edge.target}";')
    else:
        for source, target in _edges(proc, graph):
            lines.append(f'  "{source}" -> "{target}";')
    lines.append("}")
    return "\n".join(lines)


def to_sql(proc: ProcedureDivision, graph: str = "flow") -> str:
    table = "flow_edges" if graph == "flow" else "call_edges"
    lines = []
    for source, target in _edges(proc, graph):
        source_sql = source.replace("'", "''")
        target_sql = target.replace("'", "''")
        lines.append(f"INSERT INTO {table} (source, target) VALUES ('{source_sql}', '{target_sql}');")
    return "\n".join(lines)
