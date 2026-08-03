from __future__ import annotations

import json
from pprint import pformat

from .depgraph import build_call_graph
from .fileaccess import build_file_access_graph
from .flow import build_flow_graph, build_flow_graph_detailed
from .models import BranchCond, ProcedureDivision

_GRAPH_NAMES = "'flow', 'call', or 'file'"


def _file_edges(proc: ProcedureDivision) -> list[tuple[str, str]]:
    return [(e.paragraph, e.file_name) for e in build_file_access_graph(proc)]


_GRAPH_BUILDERS = {"flow": build_flow_graph, "call": build_call_graph, "file": _file_edges}


def _branch_path_json(branch_path: list[BranchCond]) -> list[dict]:
    return [{"kind": b.kind, "text": b.text} for b in branch_path]


def _file_descriptor_json(fd) -> dict:
    node = {"name": fd.name}
    if fd.organization:
        node["organization"] = fd.organization
    if fd.access_mode:
        node["access_mode"] = fd.access_mode
    if fd.record_key:
        node["record_key"] = fd.record_key
    if fd.alternate_record_keys:
        node["alternate_record_keys"] = fd.alternate_record_keys
    if fd.file_status:
        node["file_status"] = fd.file_status
    if fd.record_names:
        node["record_names"] = fd.record_names
    return node


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

    def _io(io):
        node = {"operation": io.operation, "target": io.target}
        if io.branch_path:
            node["branch_path"] = _branch_path_json(io.branch_path)
        return node

    return {
        "program_id": proc.program_id,
        "sections": proc.sections,
        "files": [_file_descriptor_json(fd) for fd in proc.files],
        "paragraphs": [
            {
                "name": p.name,
                "section": p.section,
                "performs": [_perform(s) for s in p.performs],
                "calls": [_call(c) for c in p.calls],
                "go_tos": [_goto(g) for g in p.go_tos],
                "io_statements": [_io(io) for io in p.io_statements],
            }
            for p in proc.paragraphs
        ],
        "flow_edges": build_flow_graph(proc),
        "call_edges": build_call_graph(proc),
        "file_access_edges": _file_edges(proc),
    }


def to_json(proc: ProcedureDivision, indent: int = 2) -> str:
    return json.dumps(_to_dict(proc), indent=indent, ensure_ascii=False)


def to_python(proc: ProcedureDivision) -> str:
    return pformat(_to_dict(proc))


def _edges(proc: ProcedureDivision, graph: str) -> list[tuple[str, str]]:
    if graph not in _GRAPH_BUILDERS:
        raise ValueError(f"Unknown graph {graph!r}; expected {_GRAPH_NAMES}")
    return _GRAPH_BUILDERS[graph](proc)


def _branch_label(branch_path: list[BranchCond]) -> str | None:
    if not branch_path:
        return None
    return " / ".join(f"{b.kind}: {b.text}" for b in branch_path)


def to_dot(proc: ProcedureDivision, graph: str = "flow") -> str:
    if graph not in _GRAPH_BUILDERS:
        raise ValueError(f"Unknown graph {graph!r}; expected {_GRAPH_NAMES}")

    lines = [f"digraph {graph} {{"]
    if graph == "flow":
        for edge in build_flow_graph_detailed(proc):
            label = _branch_label(edge.branch_path)
            if label:
                escaped = label.replace('"', '\\"')
                lines.append(f'  "{edge.source}" -> "{edge.target}" [label="{escaped}"];')
            else:
                lines.append(f'  "{edge.source}" -> "{edge.target}";')
    elif graph == "file":
        for edge in build_file_access_graph(proc):
            label = edge.operation
            branch_label = _branch_label(edge.branch_path)
            if branch_label:
                label += f" / {branch_label}"
            escaped = label.replace('"', '\\"')
            lines.append(f'  "{edge.paragraph}" -> "{edge.file_name}" [label="{escaped}"];')
    else:
        for source, target in _edges(proc, graph):
            lines.append(f'  "{source}" -> "{target}";')
    lines.append("}")
    return "\n".join(lines)


_SQL_TABLE_NAMES = {"flow": "flow_edges", "call": "call_edges", "file": "file_access_edges"}


def to_sql(proc: ProcedureDivision, graph: str = "flow") -> str:
    if graph not in _GRAPH_BUILDERS:
        raise ValueError(f"Unknown graph {graph!r}; expected {_GRAPH_NAMES}")
    table = _SQL_TABLE_NAMES[graph]
    lines = []
    for source, target in _edges(proc, graph):
        source_sql = source.replace("'", "''")
        target_sql = target.replace("'", "''")
        lines.append(f"INSERT INTO {table} (source, target) VALUES ('{source_sql}', '{target_sql}');")
    return "\n".join(lines)
