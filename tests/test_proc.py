"""Tests for PROCEDURE DIVISION parsing: SECTIONs, paragraphs, PERFORM/CALL."""
from __future__ import annotations

import json

from cobol_data_parser.proc.depgraph import build_call_graph
from cobol_data_parser.proc.docgen import to_markdown_spec
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
    assert main_para.calls[0].using == ["WS-REC"]
    assert main_para.calls[1].target == "WS-DYNAMIC-NAME"
    assert main_para.calls[1].dynamic is True
    assert main_para.calls[1].using == []


def test_perform_varying_until():
    cobol = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOOPER.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM LOOP-A VARYING WS-IDX FROM 1 BY 1 UNTIL WS-IDX > 10.
           PERFORM INIT-PARA.
       LOOP-A.
           DISPLAY 'A'.
       INIT-PARA.
           DISPLAY 'INIT'.
    """
    proc = parse(cobol)
    main_para = proc.paragraphs[0]
    assert main_para.performs[0].varying == "WS-IDX"
    assert main_para.performs[0].until is True
    assert main_para.performs[1].varying is None
    assert main_para.performs[1].until is False


def test_call_using_by_qualifiers_and_returning():
    cobol = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLER.
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL 'SUBPGM1' USING BY REFERENCE WS-REC BY VALUE WS-FLAG
               RETURNING WS-RESULT.
           STOP RUN.
    """
    proc = parse(cobol)
    call = proc.paragraphs[0].calls[0]
    assert call.using == ["WS-REC", "WS-FLAG"]
    assert call.returning == "WS-RESULT"


def test_go_to_adds_flow_edge():
    cobol = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. JUMPER.
       PROCEDURE DIVISION.
       MAIN-PARA.
           GO TO EXIT-PARA.
       EXIT-PARA.
           DISPLAY 'BYE'.
    """
    proc = parse(cobol)
    assert proc.paragraphs[0].go_tos[0].target == "EXIT-PARA"
    assert ("MAIN-PARA", "EXIT-PARA") in build_flow_graph(proc)


def test_evaluate_branches_are_still_scanned():
    """No branch-conditional CFG — statements inside EVALUATE/IF are still
    picked up by the flat text scan, but which WHEN/branch they belong to
    isn't tracked (see README PROCEDURE DIVISION section)."""
    cobol = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BRANCHER.
       PROCEDURE DIVISION.
       MAIN-PARA.
           EVALUATE WS-CODE
               WHEN 1
                   PERFORM CASE-ONE
               WHEN 2
                   PERFORM CASE-TWO
               WHEN OTHER
                   CALL 'FALLBACK'
           END-EVALUATE.
       CASE-ONE.
           DISPLAY '1'.
       CASE-TWO.
           DISPLAY '2'.
    """
    proc = parse(cobol)
    main_para = proc.paragraphs[0]
    targets = {p.target for p in main_para.performs}
    assert targets == {"CASE-ONE", "CASE-TWO"}
    assert main_para.calls[0].target == "FALLBACK"


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


def test_to_markdown_spec_lists_paragraphs_and_graphs():
    proc = parse(SAMPLE)
    spec = to_markdown_spec(proc)
    assert spec.startswith("# プログラム仕様書: SAMPLE-PROG")
    assert "MAIN-PARA" in spec
    assert "INIT-PARA" in spec
    assert "MAIN-PARA → INIT-PARA" in spec
    assert "SAMPLE-PROG → SUBPGM1" in spec


def test_to_markdown_spec_shows_varying_until_and_call_args():
    cobol = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOOPER.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM LOOP-A VARYING WS-IDX FROM 1 BY 1 UNTIL WS-IDX > 10.
           CALL 'SUBPGM1' USING WS-REC RETURNING WS-RESULT.
       LOOP-A.
           DISPLAY 'A'.
    """
    spec = to_markdown_spec(parse(cobol))
    assert "VARYING WS-IDX" in spec
    assert "UNTIL ..." in spec
    assert "USING WS-REC" in spec
    assert "RETURNING WS-RESULT" in spec
