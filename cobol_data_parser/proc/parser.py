from __future__ import annotations

import re

from ..common.lexer import preprocess
from .models import CallStmt, Paragraph, PerformStmt, ProcedureDivision

_PROGRAM_ID_RE = re.compile(r"^PROGRAM-ID\.\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_PROCEDURE_DIVISION_RE = re.compile(r"^PROCEDURE\s+DIVISION\b.*\.$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^([A-Z0-9][A-Z0-9-]*)\s+SECTION\.$", re.IGNORECASE)
_PARAGRAPH_RE = re.compile(r"^([A-Z0-9][A-Z0-9-]*)\.$", re.IGNORECASE)

_PERFORM_RE = re.compile(
    r"\bPERFORM\s+([A-Z0-9][A-Z0-9-]*)(?:\s+(?:THRU|THROUGH)\s+([A-Z0-9][A-Z0-9-]*))?",
    re.IGNORECASE,
)
_CALL_RE = re.compile(
    r"""\bCALL\s+(?:'([^']*)'|"([^"]*)"|([A-Z0-9][A-Z0-9-]*))""", re.IGNORECASE
)


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


def _scan_statements(name: str, section: str | None, text: str) -> Paragraph:
    para = Paragraph(name=name, section=section)
    for m in _PERFORM_RE.finditer(text):
        para.performs.append(PerformStmt(target=m.group(1).upper(), thru=(m.group(2) or None) and m.group(2).upper()))
    for m in _CALL_RE.finditer(text):
        literal = m.group(1) or m.group(2)
        if literal is not None:
            para.calls.append(CallStmt(target=literal, dynamic=False))
        else:
            para.calls.append(CallStmt(target=m.group(3).upper(), dynamic=True))
    return para


def parse(text: str, fixed_format: bool | None = None) -> ProcedureDivision:
    """Parse the PROCEDURE DIVISION of a COBOL source: SECTIONs, paragraphs,
    and their PERFORM/CALL statements.

    Only the most common forms of PERFORM, SECTION and CALL are recognized
    (single-target PERFORM/PERFORM THRU, literal or identifier CALL targets).
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
