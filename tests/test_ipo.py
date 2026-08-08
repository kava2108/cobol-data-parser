"""Tests for MOVE/ADD/SUBTRACT/MULTIPLY/DIVIDE/COMPUTE/ACCEPT/DISPLAY
parsing, the derived dataflow facts, and the IPO Markdown document
(template and LLM render modes)."""
from __future__ import annotations

import sys
import types

import pytest

from cobol_data_parser.proc.dataflow import build_dataflow_facts
from cobol_data_parser.proc.docgen import to_markdown_ipo
from cobol_data_parser.proc.parser import parse


def _first_paragraph(cobol: str):
    return parse(cobol).paragraphs[0]


def test_move_records_source_and_multiple_targets():
    cobol = """
    PROCEDURE DIVISION.
    MAIN-PARA.
        MOVE WS-A TO WS-B WS-C.
    """
    para = _first_paragraph(cobol)
    assert len(para.moves) == 1
    mv = para.moves[0]
    assert mv.source == "WS-A"
    assert mv.targets == ["WS-B", "WS-C"]
    assert mv.corresponding is False


def test_move_corresponding_and_literal_source():
    cobol = """
    PROCEDURE DIVISION.
    MAIN-PARA.
        MOVE CORRESPONDING WS-REC-A TO WS-REC-B.
        MOVE 'X' TO WS-FLAG.
    """
    para = _first_paragraph(cobol)
    assert para.moves[0].corresponding is True
    assert para.moves[1].source == "'X'"
    assert para.moves[1].targets == ["WS-FLAG"]


def test_add_to_form_writes_the_to_target():
    cobol = """
    PROCEDURE DIVISION.
    MAIN-PARA.
        ADD WS-A WS-B TO WS-TOTAL.
    """
    para = _first_paragraph(cobol)
    stmt = para.arithmetic[0]
    assert stmt.operation == "ADD"
    assert stmt.operands == ["WS-A", "WS-B"]
    assert stmt.targets == ["WS-TOTAL"]


def test_add_giving_form_does_not_leak_to_keyword_into_operands():
    cobol = """
    PROCEDURE DIVISION.
    MAIN-PARA.
        ADD WS-A TO WS-B GIVING WS-C.
    """
    para = _first_paragraph(cobol)
    stmt = para.arithmetic[0]
    assert stmt.operands == ["WS-A", "WS-B"]
    assert stmt.targets == ["WS-C"]
    assert "TO" not in stmt.operands


def test_subtract_from_form():
    cobol = """
    PROCEDURE DIVISION.
    MAIN-PARA.
        SUBTRACT WS-A FROM WS-TOTAL.
    """
    stmt = _first_paragraph(cobol).arithmetic[0]
    assert stmt.operation == "SUBTRACT"
    assert stmt.operands == ["WS-A"]
    assert stmt.targets == ["WS-TOTAL"]


def test_multiply_by_giving_form():
    cobol = """
    PROCEDURE DIVISION.
    MAIN-PARA.
        MULTIPLY WS-A BY WS-B GIVING WS-C.
    """
    stmt = _first_paragraph(cobol).arithmetic[0]
    assert stmt.operation == "MULTIPLY"
    assert stmt.operands == ["WS-A", "WS-B"]
    assert stmt.targets == ["WS-C"]


def test_divide_into_and_giving_remainder():
    cobol = """
    PROCEDURE DIVISION.
    MAIN-PARA.
        DIVIDE WS-A INTO WS-B.
        DIVIDE WS-A BY WS-B GIVING WS-C REMAINDER WS-D.
    """
    stmts = _first_paragraph(cobol).arithmetic
    assert stmts[0].operation == "DIVIDE"
    assert stmts[0].operands == ["WS-A"]
    assert stmts[0].targets == ["WS-B"]
    assert stmts[1].targets == ["WS-C", "WS-D"]
    assert "REMAINDER" not in stmts[1].targets


def test_compute_splits_target_and_expression_tokens():
    cobol = """
    PROCEDURE DIVISION.
    MAIN-PARA.
        COMPUTE WS-TOTAL = WS-A + WS-B * 2.
    """
    stmt = _first_paragraph(cobol).arithmetic[0]
    assert stmt.operation == "COMPUTE"
    assert stmt.targets == ["WS-TOTAL"]
    assert stmt.operands == ["WS-A", "WS-B", "2"]


def test_accept_with_and_without_from():
    cobol = """
    PROCEDURE DIVISION.
    MAIN-PARA.
        ACCEPT WS-DATE FROM DATE.
        ACCEPT WS-INPUT.
    """
    accepts = _first_paragraph(cobol).accepts
    assert accepts[0].target == "WS-DATE"
    assert accepts[0].from_source == "DATE"
    assert accepts[1].target == "WS-INPUT"
    assert accepts[1].from_source is None


def test_display_items_keep_literal_quotes():
    cobol = """
    PROCEDURE DIVISION.
    MAIN-PARA.
        DISPLAY WS-A "HELLO" WS-B.
    """
    stmt = _first_paragraph(cobol).displays[0]
    assert stmt.items == ["WS-A", '"HELLO"', "WS-B"]


def test_move_inside_if_carries_branch_path():
    cobol = """
    PROCEDURE DIVISION.
    MAIN-PARA.
        IF WS-A = 1
            MOVE WS-X TO WS-Y
        END-IF.
    """
    mv = _first_paragraph(cobol).moves[0]
    assert [(b.kind, b.text) for b in mv.branch_path] == [("IF", "WS-A = 1")]


SAMPLE = """
PROCEDURE DIVISION.
CALC-PARA.
    MOVE WS-A TO WS-B.
    ADD WS-B TO WS-TOTAL.
    DISPLAY WS-TOTAL.
"""


def test_build_dataflow_facts_classifies_reads_and_writes():
    proc = parse(SAMPLE)
    facts = build_dataflow_facts(proc)
    reads = {(f.item, f.stmt_kind) for f in facts if f.access == "READ"}
    writes = {(f.item, f.stmt_kind) for f in facts if f.access == "WRITE"}
    assert ("WS-A", "MOVE") in reads
    assert ("WS-B", "MOVE") in writes
    assert ("WS-B", "ADD") in reads
    assert ("WS-TOTAL", "ADD") in writes
    assert ("WS-TOTAL", "DISPLAY") in reads


def test_build_dataflow_facts_excludes_literals_and_digits():
    cobol = """
    PROCEDURE DIVISION.
    MAIN-PARA.
        MOVE 'X' TO WS-FLAG.
        COMPUTE WS-TOTAL = WS-A + 2.
    """
    facts = build_dataflow_facts(parse(cobol))
    items = {f.item for f in facts}
    assert "'X'" not in items
    assert "2" not in items


def test_to_markdown_ipo_template_default_lists_inputs_outputs_and_sentences():
    spec = to_markdown_ipo(parse(SAMPLE))
    assert "## CALC-PARA" in spec
    assert "**入力**: WS-A" in spec
    assert "WS-A を WS-B に転記する。" in spec
    assert "WS-B を WS-TOTAL に加算する。" in spec
    assert "WS-TOTAL を表示する。" in spec
    assert "**出力**: WS-B、WS-TOTAL" in spec


def test_to_markdown_ipo_skips_paragraphs_with_no_data_statements():
    cobol = """
    PROCEDURE DIVISION.
    EMPTY-PARA.
        PERFORM OTHER-PARA.
    OTHER-PARA.
        MOVE WS-A TO WS-B.
    """
    spec = to_markdown_ipo(parse(cobol))
    assert "## EMPTY-PARA" not in spec
    assert "## OTHER-PARA" in spec


def test_to_markdown_ipo_rejects_unknown_render_mode():
    with pytest.raises(ValueError):
        to_markdown_ipo(parse(SAMPLE), render="prose")


def test_llm_render_without_sdk_raises_helpful_import_error(monkeypatch):
    import cobol_data_parser.proc.llm_nlg as llm_nlg

    monkeypatch.setattr(llm_nlg, "IMPORT_ERROR", ImportError("no anthropic"))
    with pytest.raises(ImportError, match=r"pip install cobol-data-parser\[llm\]"):
        to_markdown_ipo(parse(SAMPLE), render="llm")


def test_llm_render_uses_mocked_client_and_never_calls_network(monkeypatch):
    import cobol_data_parser.proc.llm_nlg as llm_nlg

    captured = {}

    class _FakeTextBlock:
        type = "text"
        text = "WS-Aの値をWS-Bへ転記し、WS-TOTALに加算したうえで表示する。"

    class _FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(content=[_FakeTextBlock()])

    class _FakeClient:
        def __init__(self, *a, **kw):
            self.messages = _FakeMessages()

    fake_anthropic = types.SimpleNamespace(Anthropic=_FakeClient)
    monkeypatch.setattr(llm_nlg, "anthropic", fake_anthropic)
    monkeypatch.setattr(llm_nlg, "IMPORT_ERROR", None)
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

    spec = to_markdown_ipo(parse(SAMPLE), render="llm")

    assert "WS-Aの値をWS-Bへ転記し、WS-TOTALに加算したうえで表示する。" in spec
    assert "CALC-PARA" in captured["messages"][0]["content"]
    assert "**入力**: WS-A" in spec
    assert "**出力**: WS-B、WS-TOTAL" in spec
