from __future__ import annotations

import re

from ..common.lexer import preprocess
from .environment import parse_file_descriptors
from .models import BranchCond, CallStmt, GoToStmt, IoStmt, Paragraph, PerformStmt, ProcedureDivision

_PROGRAM_ID_RE = re.compile(r"^PROGRAM-ID\.\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_PROCEDURE_DIVISION_RE = re.compile(r"^PROCEDURE\s+DIVISION\b.*\.$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^([A-Z0-9][A-Z0-9-]*)\s+SECTION\.$", re.IGNORECASE)
_PARAGRAPH_RE = re.compile(r"^([A-Z0-9][A-Z0-9-]*)\.$", re.IGNORECASE)

# COBOL scope-terminator statements ('END-IF.', 'END-EVALUATE.', ...) are
# syntactically indistinguishable from a paragraph name by _PARAGRAPH_RE
# alone (both are just "<word>." on their own line) — very common when a
# scope terminator is written on its own line, e.g.:
#     IF ...
#         PERFORM X
#     END-IF.
# Without this exclusion, "END-IF." would be misread as declaring a new
# (empty) paragraph named END-IF, splitting the real paragraph in two and
# shifting paragraph order (which PERFORM THRU range expansion relies on).
_SCOPE_TERMINATORS = {
    "END-IF",
    "END-EVALUATE",
    "END-PERFORM",
    "END-READ",
    "END-WRITE",
    "END-REWRITE",
    "END-DELETE",
    "END-START",
    "END-CALL",
    "END-STRING",
    "END-UNSTRING",
    "END-COMPUTE",
    "END-ADD",
    "END-SUBTRACT",
    "END-MULTIPLY",
    "END-DIVIDE",
    "END-SEARCH",
    "END-ACCEPT",
    "END-RETURN",
}

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

# I/O statements: READ/DELETE/START take a file-name; WRITE/REWRITE take a
# record-name (the file is only implied, via whichever FD owns that record —
# see IoStmt's docstring in models.py). 'READ NEXT RECORD' etc. optional
# keywords between the file-name and the rest of the statement don't affect
# the target capture, since only the first identifier after the keyword is
# taken.
#
# Lookaround-bounded, not \b: their own scope terminators (END-READ,
# END-WRITE, END-REWRITE, END-DELETE, END-START) end with the same word, and
# \b treats '-' as a non-word character — \bREAD\s+(...) would match the
# 'READ' inside 'END-READ WRITE ...' and capture 'WRITE' as a bogus target.
_READ_RE = re.compile(r"(?<![A-Z0-9-])READ\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_WRITE_RE = re.compile(r"(?<![A-Z0-9-])WRITE\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_REWRITE_RE = re.compile(r"(?<![A-Z0-9-])REWRITE\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_DELETE_RE = re.compile(r"(?<![A-Z0-9-])DELETE\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_START_RE = re.compile(r"(?<![A-Z0-9-])START\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_IO_PATTERNS = (
    ("READ", _READ_RE),
    ("WRITE", _WRITE_RE),
    ("REWRITE", _REWRITE_RE),
    ("DELETE", _DELETE_RE),
    ("START", _START_RE),
)

# Heuristic statement boundary: where to stop looking for a CALL's USING/
# RETURNING clause (and, for IF/WHEN, where a condition/value ends and the
# statement body begins), since statements aren't otherwise delimited once
# joined into one text blob per paragraph.
#
# The boundary is anchored with lookaround rather than \b: COBOL data-names
# are hyphenated (e.g. WS-IF-SWITCH), and \b treats '-' as a non-word
# character, so \bIF\b would false-match the 'IF' inside such a name. This
# matters more here than it used to: a false match doesn't just mis-bound a
# clause anymore, it can desync the IF/EVALUATE nesting stack in
# _split_branches below.
_STATEMENT_BOUNDARY_RE = re.compile(
    r"(?<![A-Z0-9-])(?:PERFORM|CALL|DISPLAY|MOVE|IF|END-CALL|GO\s+TO|COMPUTE|ADD|SUBTRACT|"
    r"EVALUATE|STOP\s+RUN|READ|WRITE|REWRITE|DELETE|START)(?![A-Z0-9-])",
    re.IGNORECASE,
)
_USING_RE = re.compile(r"\bUSING\s+(.+?)(?=\bRETURNING\b|$)", re.IGNORECASE | re.DOTALL)
_RETURNING_RE = re.compile(r"\bRETURNING\s+([A-Z0-9][A-Z0-9-]*)", re.IGNORECASE)
_BY_QUALIFIER_RE = re.compile(r"\bBY\s+(?:REFERENCE|CONTENT|VALUE)\b", re.IGNORECASE)
_ARG_TOKEN_RE = re.compile(r"[A-Z0-9][A-Z0-9-]*")

# Structural keywords that delimit IF/EVALUATE nesting for _split_branches.
# Same lookaround-boundary rationale as _STATEMENT_BOUNDARY_RE above. Longer
# alternatives (END-IF, END-EVALUATE) are listed before their prefixes (IF,
# EVALUATE) so a leftmost scan consumes the longer token whole.
_BRANCH_KEYWORD_RE = re.compile(
    r"(?<![A-Z0-9-])(END-IF|END-EVALUATE|IF|ELSE|EVALUATE|WHEN)(?![A-Z0-9-])",
    re.IGNORECASE,
)
_WHEN_OTHER_RE = re.compile(r"^\s*OTHER(?![A-Z0-9-])", re.IGNORECASE)


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


def _split_branches(text: str) -> list[tuple[str, list[BranchCond]]]:
    """Split paragraph text into (segment_text, branch_path) pieces along
    IF/ELSE/END-IF and EVALUATE/WHEN/END-EVALUATE boundaries.

    Only the explicit scope-terminator style is recognized (END-IF /
    END-EVALUATE) — the older implicit-scope form (terminated by the next
    period instead of an explicit END-IF/END-EVALUATE) is out of scope: a
    block that never closes just leaves the rest of the paragraph nested
    under it (best-effort, no exception raised).

    There's no delimiter between "IF <condition>" and its body (THEN is
    optional in COBOL), so the boundary between them is found the same way
    _clause_text finds a CALL's USING/RETURNING boundary: search the chunk
    for the first token _STATEMENT_BOUNDARY_RE recognizes as a statement
    keyword: everything before that is the condition/WHEN-value text,
    everything from it onward is the body. That text is captured verbatim
    as a label, not parsed as a COBOL expression. Compound WHEN forms
    (`WHEN 1 2 3`, `WHEN 1 THRU 5`) are captured whole as one label rather
    than split into individual values.
    """
    parts = _BRANCH_KEYWORD_RE.split(text)
    segments: list[tuple[str, list[BranchCond]]] = [(parts[0], [])]
    stack: list[dict] = []

    def active_path() -> list[BranchCond]:
        return stack[-1]["active_path"] if stack else []

    def cond_and_body(chunk: str) -> tuple[str, str]:
        m = _STATEMENT_BOUNDARY_RE.search(chunk)
        if m:
            return chunk[: m.start()].strip(), chunk[m.start() :]
        return chunk.strip(), ""

    i = 1
    while i < len(parts):
        keyword = parts[i].upper()
        chunk = parts[i + 1]
        i += 2

        if keyword == "IF":
            cond, body = cond_and_body(chunk)
            parent_path = active_path()
            frame = {
                "kind": "IF",
                "parent_path": parent_path,
                "cond": cond,
                "active_path": parent_path + [BranchCond("IF", cond)],
            }
            stack.append(frame)
            segments.append((body, frame["active_path"]))

        elif keyword == "ELSE" and stack and stack[-1]["kind"] == "IF":
            frame = stack[-1]
            frame["active_path"] = frame["parent_path"] + [BranchCond("IF-ELSE", frame["cond"])]
            segments.append((chunk, frame["active_path"]))

        elif keyword == "END-IF":
            if stack and stack[-1]["kind"] == "IF":
                stack.pop()
            segments.append((chunk, active_path()))

        elif keyword == "EVALUATE":
            parent_path = active_path()
            stack.append(
                {
                    "kind": "EVALUATE",
                    "parent_path": parent_path,
                    "subject": chunk.strip(),
                    "active_path": parent_path,
                }
            )
            # `chunk` is the EVALUATE subject expression, not executable
            # body text, so it doesn't become a segment of its own.

        elif keyword == "WHEN" and stack and stack[-1]["kind"] == "EVALUATE":
            frame = stack[-1]
            if _WHEN_OTHER_RE.match(chunk):
                body = _WHEN_OTHER_RE.sub("", chunk, count=1)
                frame["active_path"] = frame["parent_path"] + [
                    BranchCond("EVALUATE-WHEN-OTHER", frame["subject"])
                ]
            else:
                value, body = cond_and_body(chunk)
                frame["active_path"] = frame["parent_path"] + [
                    BranchCond("EVALUATE-WHEN", f"{frame['subject']} = {value}")
                ]
            segments.append((body, frame["active_path"]))

        elif keyword == "END-EVALUATE":
            if stack and stack[-1]["kind"] == "EVALUATE":
                stack.pop()
            segments.append((chunk, active_path()))

        else:
            # ELSE/WHEN with no matching open frame (malformed input) —
            # treat the chunk as plain text at the current level.
            segments.append((chunk, active_path()))

    return segments


def _scan_segment(para: Paragraph, text: str, branch_path: list[BranchCond]) -> None:
    for m in _PERFORM_RE.finditer(text):
        until = bool(_UNTIL_RE.search(_clause_text(text, m.end())))
        para.performs.append(
            PerformStmt(
                target=m.group(1).upper(),
                thru=m.group(2).upper() if m.group(2) else None,
                varying=m.group(3).upper() if m.group(3) else None,
                until=until,
                branch_path=branch_path,
            )
        )

    for m in _CALL_RE.finditer(text):
        literal = m.group(1) or m.group(2)
        using, returning = _call_using_returning(text, m.end())
        if literal is not None:
            para.calls.append(
                CallStmt(target=literal, dynamic=False, using=using, returning=returning, branch_path=branch_path)
            )
        else:
            para.calls.append(
                CallStmt(
                    target=m.group(3).upper(),
                    dynamic=True,
                    using=using,
                    returning=returning,
                    branch_path=branch_path,
                )
            )

    for m in _GOTO_RE.finditer(text):
        para.go_tos.append(GoToStmt(target=m.group(1).upper(), branch_path=branch_path))

    for operation, pattern in _IO_PATTERNS:
        for m in pattern.finditer(text):
            para.io_statements.append(
                IoStmt(operation=operation, target=m.group(1).upper(), branch_path=branch_path)
            )


def _scan_statements(name: str, section: str | None, text: str) -> Paragraph:
    para = Paragraph(name=name, section=section)
    for segment_text, branch_path in _split_branches(text):
        _scan_segment(para, segment_text, branch_path)
    return para


def parse(
    text: str,
    fixed_format: bool | None = None,
    copybook_dirs: list[str] | None = None,
) -> ProcedureDivision:
    """Parse a COBOL source's ENVIRONMENT DIVISION/DATA DIVISION file
    declarations and PROCEDURE DIVISION SECTIONs, paragraphs, and their
    PERFORM/CALL/GO TO/READ/WRITE/REWRITE/DELETE/START statements.

    Only the most common forms are recognized: PERFORM with an optional THRU
    range and VARYING identifier (the UNTIL condition's presence is noted,
    not its expression text), literal or identifier CALL targets with USING/
    RETURNING, single-target GO TO, and READ/WRITE/REWRITE/DELETE/START each
    with their file- or record-name target (see IoStmt in models.py — AT
    END/INVALID KEY clauses aren't modeled as branches). Statements are
    found by scanning each paragraph's text with regexes rather than a real
    COBOL statement grammar.

    Statements nested inside IF/ELSE or EVALUATE/WHEN blocks carry a
    `branch_path` (see BranchCond in models.py) recording which branch(es)
    they're under — but only for the explicit scope-terminator style
    (END-IF/END-EVALUATE); the older implicit-scope style (terminated by the
    next period) isn't recognized as a block boundary. Condition/WHEN-value
    text is captured verbatim as a label, not parsed as a COBOL expression.

    `copybook_dirs`, if given, expands COPY statements found while scanning
    FILE SECTION FD entries (see environment.py's parse_file_descriptors()).
    """
    logical = preprocess(text, fixed_format=fixed_format)
    program_id = _find_program_id(logical)
    files = parse_file_descriptors(text, fixed_format=fixed_format, copybook_dirs=copybook_dirs)
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
        if para_m and para_m.group(1).upper() not in _SCOPE_TERMINATORS:
            flush()
            current_name = para_m.group(1).upper()
            current_buffer = []
            continue

        if current_name is None:
            # Statements appearing before any explicit paragraph name.
            current_name = current_section or "MAIN"
        current_buffer.append(line)

    flush()

    return ProcedureDivision(program_id=program_id, sections=sections, paragraphs=paragraphs, files=files)
