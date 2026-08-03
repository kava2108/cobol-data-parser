"""Tests for PROCEDURE DIVISION parsing: SECTIONs, paragraphs, PERFORM/CALL."""
from __future__ import annotations

import json

from cobol_data_parser.proc.depgraph import build_call_graph
from cobol_data_parser.proc.emitter import to_dot, to_json, to_python, to_sql
from cobol_data_parser.proc.flow import build_flow_graph
from cobol_data_parser.proc.parser import parse

SAMPLE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SAMPLE-PROG.
       PROCEDURE DIVISION.
       MAIN-SECTION SECTION.
       MAIN-PARA.
           PERFORM INIT-PARA.
           PERFORM LOOP-A THRU LOOP-C.
           CALL 'SUBPGM1' USING WS-REC.
           CALL WS-DYNAMIC-NAME.
           STOP RUN.
       INIT-PARA.
           DISPLAY 'INIT'.
       LOOP-A.
           DISPLAY 'A'.
       LOOP-B.
           DISPLAY 'B'.
       LOOP-C.
           DISPLAY 'C'.
"""


def test_program_id_and_sections():
    proc = parse(SAMPLE)
    assert proc.program_id == "SAMPLE-PROG"
    assert proc.sections == ["MAIN-SECTION"]


def test_paragraphs_and_performs():
    proc = parse(SAMPLE)
    names = [p.name for p in proc.paragraphs]
    assert names == ["MAIN-PARA", "INIT-PARA", "LOOP-A", "LOOP-B", "LOOP-C"]

    main_para = proc.paragraphs[0]
    assert main_para.performs[0].target == "INIT-PARA"
    assert main_para.performs[0].thru is None
    assert main_para.performs[1].target == "LOOP-A"
    assert main_para.performs[1].thru == "LOOP-C"


def test_calls_literal_and_dynamic():
    proc = parse(SAMPLE)
    main_para = proc.paragraphs[0]
    assert main_para.calls[0].target == "SUBPGM1"
    assert main_para.calls[0].dynamic is False
    assert main_para.calls[1].target == "WS-DYNAMIC-NAME"
    assert main_para.calls[1].dynamic is True


def test_flow_graph_expands_thru_range():
    proc = parse(SAMPLE)
    edges = build_flow_graph(proc)
    assert ("MAIN-PARA", "INIT-PARA") in edges
    assert ("MAIN-PARA", "LOOP-A") in edges
    assert ("MAIN-PARA", "LOOP-B") in edges
    assert ("MAIN-PARA", "LOOP-C") in edges


def test_call_graph_uses_program_id_and_marks_dynamic():
    proc = parse(SAMPLE)
    edges = build_call_graph(proc)
    assert ("SAMPLE-PROG", "SUBPGM1") in edges
    assert ("SAMPLE-PROG", "DYNAMIC:WS-DYNAMIC-NAME") in edges


def test_to_json_roundtrip():
    proc = parse(SAMPLE)
    data = json.loads(to_json(proc))
    assert data["program_id"] == "SAMPLE-PROG"
    assert len(data["paragraphs"]) == 5


def test_to_dot_contains_edges():
    proc = parse(SAMPLE)
    dot = to_dot(proc, graph="flow")
    assert dot.startswith("digraph flow {")
    assert '"MAIN-PARA" -> "INIT-PARA";' in dot


def test_to_sql_contains_insert_statements():
    proc = parse(SAMPLE)
    sql = to_sql(proc, graph="call")
    assert "INSERT INTO call_edges (source, target) VALUES ('SAMPLE-PROG', 'SUBPGM1');" in sql


def test_to_python_is_valid_literal():
    proc = parse(SAMPLE)
    text = to_python(proc)
    assert "SAMPLE-PROG" in text
