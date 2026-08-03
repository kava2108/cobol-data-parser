from __future__ import annotations

import json
from pprint import pformat

from .depgraph import build_call_graph
from .flow import build_flow_graph
from .models import ProcedureDivision

_GRAPH_BUILDERS = {"flow": build_flow_graph, "call": build_call_graph}


def _to_dict(proc: ProcedureDivision) -> dict:
    return {
        "program_id": proc.program_id,
        "sections": proc.sections,
        "paragraphs": [
            {
                "name": p.name,
                "section": p.section,
                "performs": [{"target": s.target, "thru": s.thru} for s in p.performs],
                "calls": [{"target": c.target, "dynamic": c.dynamic} for c in p.calls],
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


def to_dot(proc: ProcedureDivision, graph: str = "flow") -> str:
    lines = [f"digraph {graph} {{"]
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
