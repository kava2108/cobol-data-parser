"""PROCEDURE DIVISION analysis: control-flow and CALL dependency graphs."""

from .depgraph import build_call_graph
from .docgen import to_markdown_spec
from .emitter import to_dot, to_json, to_python, to_sql
from .flow import FlowEdge, build_flow_graph, build_flow_graph_detailed
from .models import BranchCond, CallStmt, GoToStmt, Paragraph, PerformStmt, ProcedureDivision
from .parser import parse

__all__ = [
    "parse",
    "build_flow_graph",
    "build_flow_graph_detailed",
    "build_call_graph",
    "to_json",
    "to_dot",
    "to_sql",
    "to_python",
    "to_markdown_spec",
    "ProcedureDivision",
    "Paragraph",
    "PerformStmt",
    "CallStmt",
    "GoToStmt",
    "BranchCond",
    "FlowEdge",
]
