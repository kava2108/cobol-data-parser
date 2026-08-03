from __future__ import annotations

import re

from ..common.lexer import preprocess
from .models import CallStmt, GoToStmt, Paragraph, PerformStmt, ProcedureDivision

_PROGRAM_ID_RE = re.compile(r"^PROGRAM-ID\.\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_PROCEDURE_DIVISION_RE = re.compile(r"^PROCEDURE\s+DIVISION\b.*\.$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^([A-Z0-9][A-Z0-9-]*)\s+SECTION\.$", re.IGNORECASE)
_PARAGRAPH_RE = re.compile(r"^([A-Z0-9][A-Z0-9-]*)\.$", re.IGNORECASE)

# Negative lookahead excludes the inline-loop forms 'PERFORM UNTIL ...' and
# 'PERFORM VARYING ...' (no paragraph target — a target-less in-line PERFORM
# isn't a control-flow edge to anything).
_PERFORM_RE = re.compile(
    r"\bPERFORM\s+(?!UNTIL\b|VARYING\b|WITH\b)([A-Z0-9][A-Z0-9-]*)"
    r"(?:\s+(?:THRU|THROUGH)\s+([A-Z0-9][A-Z0-9-]*))?"
    r"(?:\s+VARYING\s+([A-Z0-9][A-Z0-9-]*))?",
    re.IGNORECASE,
)
_UNTIL_RE = re.compile(r"\bUNTIL\b", re.IGNORECASE)
_CALL_RE = re.compile(
    r"""\bCALL\s+(?:'([^']*)'|"([^"]*)"|([A-Z0-9][A-Z0-9-]*))""", re.IGNORECASE
)
_GOTO_RE = re.compile(r"\bGO\s+TO\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)

# Heuristic statement boundary: where to stop looking for a CALL's USING/
# RETURNING clause, since statements aren't otherwise delimited once joined
# into one text blob per paragraph.
_STATEMENT_BOUNDARY_RE = re.compile(
    r"\b(?:PERFORM|CALL|DISPLAY|MOVE|IF|END-CALL|GO\s+TO|COMPUTE|ADD|SUBTRACT|EVALUATE|STOP\s+RUN)\b",
    re.IGNORECASE,
)
_USING_RE = re.compile(r"\bUSING\s+(.+?)(?=\bRETURNING\b|$)", re.IGNORECASE | re.DOTALL)
_RETURNING_RE = re.compile(r"\bRETURNING\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_BY_QUALIFIER_RE = re.compile(r"\bBY\s+(?:REFERENCE|CONTENT|VALUE)\b", re.IGNORECASE)
_ARG_TOKEN_RE = re.compile(r"[A-Z0-9][A-Z0-9-]*")


def _find_program_id(logical_lines: list[str]) -> str | None:
    for line in logical_lines:
        m = _PROGRAM_ID_RE.match(line.strip())
        if m:
            return m.group(1).upper()
    return None


def _procedure_division_lines(logical_lines: list[str]) -> list[str]:
    """Return logical lines that fall after the PROCEDURE DIVISION header."""
    for i, line in enumerate(logical_lines):
        if _PROCEDURE_DIVISION_RE.match(line.strip()):
            return logical_lines[i + 1 :]
    return []


def _clause_text(text: str, match_end: int) -> str:
    """Text between the end of a statement match and the next likely
    statement-starting keyword, since statements within a paragraph aren't
    otherwise delimited once joined into one text blob."""
    tail = text[match_end:]
    boundary = _STATEMENT_BOUNDARY_RE.search(tail)
    return tail[: boundary.start()] if boundary else tail


def _call_using_returning(text: str, call_end: int) -> tuple[list[str], str | None]:
    """Extract a CALL's USING argument identifiers and RETURNING target."""
    clause_text = _clause_text(text, call_end)

    using: list[str] = []
    m_using = _USING_RE.search(clause_text)
    if m_using:
        cleaned = _BY_QUALIFIER_RE.sub(" ", m_using.group(1))
        using = [tok.upper() for tok in _ARG_TOKEN_RE.findall(cleaned)]

    returning = None
    m_returning = _RETURNING_RE.search(clause_text)
    if m_returning:
        returning = m_returning.group(1).upper()

    return using, returning


def _scan_statements(name: str, section: str | None, text: str) -> Paragraph:
    para = Paragraph(name=name, section=section)

    for m in _PERFORM_RE.finditer(text):
        until = bool(_UNTIL_RE.search(_clause_text(text, m.end())))
        para.performs.append(
            PerformStmt(
                target=m.group(1).upper(),
                thru=m.group(2).upper() if m.group(2) else None,
                varying=m.group(3).upper() if m.group(3) else None,
                until=until,
            )
        )

    for m in _CALL_RE.finditer(text):
        literal = m.group(1) or m.group(2)
        using, returning = _call_using_returning(text, m.end())
        if literal is not None:
            para.calls.append(CallStmt(target=literal, dynamic=False, using=using, returning=returning))
        else:
            para.calls.append(
                CallStmt(target=m.group(3).upper(), dynamic=True, using=using, returning=returning)
            )

    for m in _GOTO_RE.finditer(text):
        para.go_tos.append(GoToStmt(target=m.group(1).upper()))

    return para


def parse(text: str, fixed_format: bool | None = None) -> ProcedureDivision:
    """Parse the PROCEDURE DIVISION of a COBOL source: SECTIONs, paragraphs,
    and their PERFORM/CALL/GO TO statements.

    Only the most common forms are recognized: PERFORM with an optional THRU
    range and VARYING identifier (the UNTIL condition's presence is noted,
    not its expression text), literal or identifier CALL targets with USING/
    RETURNING, and single-target GO TO. Statements are found by scanning each
    paragraph's full text with regexes rather than a real COBOL statement
    grammar, so nested/conditional statements (inside IF/EVALUATE) are still
    picked up, but there's no way to tell which branch they belong to.
    """
    logical = preprocess(text, fixed_format=fixed_format)
    program_id = _find_program_id(logical)
    proc_lines = _procedure_division_lines(logical)

    sections: list[str] = []
    paragraphs: list[Paragraph] = []
    current_section: str | None = None
    current_name: str | None = None
    current_buffer: list[str] = []

    def flush() -> None:
        if current_name is not None:
            paragraphs.append(_scan_statements(current_name, current_section, " ".join(current_buffer)))

    for raw_line in proc_lines:
        line = raw_line.strip()
        if not line:
            continue

        sec_m = _SECTION_RE.match(line)
        if sec_m:
            flush()
            current_section = sec_m.group(1).upper()
            sections.append(current_section)
            current_name = None
            current_buffer = []
            continue

        para_m = _PARAGRAPH_RE.match(line)
        if para_m:
            flush()
            current_name = para_m.group(1).upper()
            current_buffer = []
            continue

        if current_name is None:
            # Statements appearing before any explicit paragraph name.
            current_name = current_section or "MAIN"
        current_buffer.append(line)

    flush()

    return ProcedureDivision(program_id=program_id, sections=sections, paragraphs=paragraphs)
