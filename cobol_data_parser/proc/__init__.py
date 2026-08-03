"""PROCEDURE DIVISION analysis: control-flow, CALL dependency, and file access graphs."""

from .depgraph import build_call_graph
from .docgen import to_markdown_spec
from .emitter import to_dot, to_json, to_python, to_sql
from .environment import parse_file_descriptors
from .fileaccess import FileAccessEdge, build_file_access_graph
from .flow import FlowEdge, build_flow_graph, build_flow_graph_detailed
from .models import (
    BranchCond,
    CallStmt,
    FileDescriptor,
    GoToStmt,
    IoStmt,
    Paragraph,
    PerformStmt,
    ProcedureDivision,
)
from .parser import parse

__all__ = [
    "parse",
    "build_flow_graph",
    "build_flow_graph_detailed",
    "build_call_graph",
    "build_file_access_graph",
    "parse_file_descriptors",
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
    "IoStmt",
    "FileDescriptor",
    "BranchCond",
    "FlowEdge",
    "FileAccessEdge",
]
