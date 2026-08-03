"""Tests for ENVIRONMENT DIVISION/FILE SECTION file-access analysis:
FileDescriptor scanning (environment.py), READ/WRITE/REWRITE/DELETE/START
statement tracking (parser.py), and the file access graph (fileaccess.py).
"""
from __future__ import annotations

from cobol_data_parser.proc.emitter import to_dot, to_json, to_sql
from cobol_data_parser.proc.environment import parse_file_descriptors
from cobol_data_parser.proc.fileaccess import build_file_access_graph
from cobol_data_parser.proc.parser import parse

VSAM_SAMPLE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. VSAMDEMO.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CUSTOMER-FILE ASSIGN TO "CUSTOMER.DAT"
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS CUST-KEY
               ALTERNATE RECORD KEY IS CUST-NAME-KEY
               FILE STATUS IS WS-FILE-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  CUSTOMER-FILE.
       01  CUSTOMER-RECORD.
           05 CUST-KEY       PIC X(10).
           05 CUST-NAME-KEY  PIC X(20).
       WORKING-STORAGE SECTION.
       01 WS-FILE-STATUS PIC XX.
       01 WS-FLAG PIC X.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-FLAG = 'Y'
               READ CUSTOMER-FILE
                   AT END DISPLAY 'EOF'
               END-READ
               WRITE CUSTOMER-RECORD
           END-IF.
           STOP RUN.
"""


def test_select_clause_fields_are_extracted():
    files = parse_file_descriptors(VSAM_SAMPLE)
    assert len(files) == 1
    fd = files[0]
    assert fd.name == "CUSTOMER-FILE"
    assert fd.organization == "INDEXED"
    assert fd.access_mode == "DYNAMIC"
    assert fd.record_key == "CUST-KEY"
    assert fd.alternate_record_keys == ["CUST-NAME-KEY"]
    assert fd.file_status == "WS-FILE-STATUS"
    assert fd.record_names == ["CUSTOMER-RECORD"]


def test_assign_to_literal_with_embedded_period_does_not_break_scanning():
    """Regression: ASSIGN TO "CUSTOMER.DAT" has a period inside the quoted
    literal — a naive period-split would cut the SELECT clause in half and
    lose ORGANIZATION/RECORD KEY/etc. to an unrecognized fragment."""
    files = parse_file_descriptors(VSAM_SAMPLE)
    fd = files[0]
    assert fd.organization == "INDEXED"
    assert fd.record_key == "CUST-KEY"


def test_fd_scope_ends_at_next_section():
    """Record names are only collected for the FD they physically follow —
    once WORKING-STORAGE SECTION starts, further 01-level items don't get
    added to the FD's record_names."""
    files = parse_file_descriptors(VSAM_SAMPLE)
    fd = files[0]
    assert "WS-FILE-STATUS" not in fd.record_names
    assert "WS-FLAG" not in fd.record_names


def test_multiple_records_under_one_fd():
    cobol = """
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT MASTER-FILE ASSIGN TO MASTER.
       DATA DIVISION.
       FILE SECTION.
       FD  MASTER-FILE.
       01  MASTER-RECORD-TYPE-A.
           05 FIELD-A PIC X(5).
       01  MASTER-RECORD-TYPE-B.
           05 FIELD-B PIC 9(5).
       PROCEDURE DIVISION.
       MAIN-PARA.
           STOP RUN.
    """
    files = parse_file_descriptors(cobol)
    assert files[0].record_names == ["MASTER-RECORD-TYPE-A", "MASTER-RECORD-TYPE-B"]


def test_copybook_expansion_inside_file_section(tmp_path):
    cpy = tmp_path / "CUST-LAYOUT.cpy"
    cpy.write_text("05 CUST-KEY PIC X(10).\n05 CUST-NAME PIC X(20).\n")

    cobol = """
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CUSTOMER-FILE ASSIGN TO CUSTOMER.
       DATA DIVISION.
       FILE SECTION.
       FD  CUSTOMER-FILE.
       01  CUSTOMER-RECORD.
           COPY CUST-LAYOUT.
       PROCEDURE DIVISION.
       MAIN-PARA.
           STOP RUN.
    """
    files = parse_file_descriptors(cobol, copybook_dirs=[tmp_path])
    assert files[0].record_names == ["CUSTOMER-RECORD"]


def test_io_statements_carry_branch_path():
    proc = parse(VSAM_SAMPLE)
    main_para = proc.paragraphs[0]
    read = next(io for io in main_para.io_statements if io.operation == "READ")
    write = next(io for io in main_para.io_statements if io.operation == "WRITE")
    assert read.target == "CUSTOMER-FILE"
    assert [(b.kind, b.text) for b in read.branch_path] == [("IF", "WS-FLAG = 'Y'")]
    assert write.target == "CUSTOMER-RECORD"
    assert [(b.kind, b.text) for b in write.branch_path] == [("IF", "WS-FLAG = 'Y'")]


def test_read_end_read_write_sequence_is_not_misparsed():
    """Regression: \\bREAD\\s+(...) previously matched the 'READ' inside
    'END-READ', capturing the following WRITE statement's keyword as a
    bogus READ target."""
    proc = parse(VSAM_SAMPLE)
    main_para = proc.paragraphs[0]
    targets_by_op = {(io.operation, io.target) for io in main_para.io_statements}
    assert targets_by_op == {("READ", "CUSTOMER-FILE"), ("WRITE", "CUSTOMER-RECORD")}


def test_build_file_access_graph_resolves_write_record_to_file():
    proc = parse(VSAM_SAMPLE)
    edges = build_file_access_graph(proc)
    by_op = {e.operation: e for e in edges}
    assert by_op["READ"].file_name == "CUSTOMER-FILE"
    assert by_op["WRITE"].file_name == "CUSTOMER-FILE"
    assert [(b.kind, b.text) for b in by_op["WRITE"].branch_path] == [("IF", "WS-FLAG = 'Y'")]


def test_unresolvable_write_target_falls_back_to_unresolved_prefix():
    cobol = """
       PROCEDURE DIVISION.
       MAIN-PARA.
           WRITE UNKNOWN-RECORD.
    """
    proc = parse(cobol)
    edges = build_file_access_graph(proc)
    assert edges[0].file_name == "UNRESOLVED:UNKNOWN-RECORD"


def test_ambiguous_record_name_across_two_fds_is_unresolved():
    cobol = """
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT FILE-A ASSIGN TO A.
           SELECT FILE-B ASSIGN TO B.
       DATA DIVISION.
       FILE SECTION.
       FD  FILE-A.
       01  SHARED-RECORD.
           05 FIELD-A PIC X(5).
       FD  FILE-B.
       01  SHARED-RECORD.
           05 FIELD-B PIC 9(5).
       PROCEDURE DIVISION.
       MAIN-PARA.
           WRITE SHARED-RECORD.
    """
    proc = parse(cobol)
    edges = build_file_access_graph(proc)
    assert edges[0].file_name == "UNRESOLVED:SHARED-RECORD"


def test_to_json_includes_files_and_file_access_edges():
    import json

    proc = parse(VSAM_SAMPLE)
    data = json.loads(to_json(proc))
    assert data["files"][0]["name"] == "CUSTOMER-FILE"
    assert data["files"][0]["organization"] == "INDEXED"
    assert data["paragraphs"][0]["io_statements"][0]["operation"] == "READ"
    assert ["MAIN-PARA", "CUSTOMER-FILE"] in data["file_access_edges"]


def test_to_dot_graph_file_labels_operation_and_branch():
    proc = parse(VSAM_SAMPLE)
    dot = to_dot(proc, graph="file")
    assert dot.startswith("digraph file {")
    assert '"MAIN-PARA" -> "CUSTOMER-FILE" [label="READ / IF: WS-FLAG = \'Y\'"];' in dot


def test_to_sql_graph_file_uses_file_access_edges_table():
    proc = parse(VSAM_SAMPLE)
    sql = to_sql(proc, graph="file")
    assert "INSERT INTO file_access_edges (source, target) VALUES ('MAIN-PARA', 'CUSTOMER-FILE');" in sql


def test_to_dot_unknown_graph_still_raises():
    proc = parse(VSAM_SAMPLE)
    try:
        to_dot(proc, graph="bogus")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "file" in str(exc)
