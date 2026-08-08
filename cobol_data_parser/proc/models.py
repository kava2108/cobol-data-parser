from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BranchCond:
    """A single IF/EVALUATE branch a statement is nested under.

    `kind` is one of "IF", "IF-ELSE", "EVALUATE-WHEN", "EVALUATE-WHEN-OTHER".
    `text` is the raw condition/subject-and-value text captured verbatim —
    it isn't parsed as a COBOL expression, just recorded as a label (same
    treatment as PerformStmt.until below). Only the explicit scope-terminator
    style (END-IF/END-EVALUATE) is recognized; see parser.py's docstring.
    """

    kind: str
    text: str


@dataclass
class PerformStmt:
    """A PERFORM <target> [THRU <thru>] [VARYING <varying>] [UNTIL ...] statement.

    `until` only records whether an UNTIL clause is present (a looping
    PERFORM) — the condition expression itself isn't parsed, since that
    requires full COBOL expression grammar, out of scope for this tool.

    `branch_path` lists the IF/EVALUATE branches this statement is nested
    under, outermost first; empty when the statement is unconditional.
    """

    target: str
    thru: str | None = None
    varying: str | None = None
    until: bool = False
    branch_path: list[BranchCond] = field(default_factory=list)


@dataclass
class CallStmt:
    """A CALL statement. `dynamic` is True when the target is an identifier
    (resolved at runtime) rather than a literal program-name. `using` lists
    argument identifiers (BY REFERENCE/CONTENT/VALUE qualifiers stripped).

    `branch_path` — see PerformStmt.
    """

    target: str
    dynamic: bool = False
    using: list[str] = field(default_factory=list)
    returning: str | None = None
    branch_path: list[BranchCond] = field(default_factory=list)


@dataclass
class GoToStmt:
    """A GO TO <target> statement.

    The regex engine (parser.py) only recognizes the single-target form, so
    `target` is always its sole target and `targets`/`depending_on` stay
    None. The ANTLR4 engine (antlr_engine/) also understands the older
    'GO TO a b c DEPENDING ON x' multi-target form: `targets` then holds all
    of them (with `target` == targets[0] for backward compatibility) and
    `depending_on` holds the DEPENDING ON identifier.

    `branch_path` — see PerformStmt.
    """

    target: str
    branch_path: list[BranchCond] = field(default_factory=list)
    targets: list[str] | None = None
    depending_on: str | None = None


@dataclass
class IoStmt:
    """A READ/WRITE/REWRITE/DELETE/START statement against a file.

    `operation` is one of "READ", "WRITE", "REWRITE", "DELETE", "START".
    `target` is the raw identifier as written: for READ/DELETE/START this is
    a *file-name* (COBOL: `READ <file-name>`), but for WRITE/REWRITE it's a
    *record-name* (COBOL: `WRITE <record-name>`) — the file is only implied,
    via whichever FD owns that record. Resolving a record-name back to its
    file-name is deliberately not done here; see fileaccess.py's
    build_file_access_graph(), which is the only place that needs it.

    `branch_path` — see PerformStmt. Note that AT END/NOT AT END (on READ)
    and INVALID KEY/NOT INVALID KEY (on WRITE/REWRITE/DELETE/START) are
    *not* modeled as branches — _split_branches() only recognizes IF/
    EVALUATE, so an imperative statement inside one of those clauses simply
    inherits whatever IF/EVALUATE branch_path is already active.
    """

    operation: str
    target: str
    branch_path: list[BranchCond] = field(default_factory=list)


@dataclass
class MoveStmt:
    """A MOVE <source> TO <target1> [<target2> ...] statement.

    `source` is the raw sending identifier or literal as written (quoted
    literals keep their surrounding quotes so they're distinguishable from
    identifiers by IPO rendering). `targets` lists every receiving
    identifier — MOVE supports multiple TO targets. MOVE CORRESPONDING is
    not decomposed into per-field moves; `corresponding` just records
    whether the keyword was present.

    `branch_path` — see PerformStmt.
    """

    source: str
    targets: list[str] = field(default_factory=list)
    corresponding: bool = False
    branch_path: list[BranchCond] = field(default_factory=list)


@dataclass
class ArithmeticStmt:
    """An ADD/SUBTRACT/MULTIPLY/DIVIDE/COMPUTE statement.

    `operation` is one of "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "COMPUTE".
    `operands` are the identifiers/literals read (for COMPUTE, every
    identifier-shaped token found in the right-hand expression — the
    expression itself isn't parsed, same "presence, not structure" treatment
    as PerformStmt.until). `targets` are the identifiers written: the GIVING
    target(s) when present, otherwise the TO/FROM/BY/INTO operand(s) that
    COBOL updates in place (e.g. plain `ADD A TO B` writes B).

    `branch_path` — see PerformStmt.
    """

    operation: str
    operands: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    branch_path: list[BranchCond] = field(default_factory=list)


@dataclass
class AcceptStmt:
    """An ACCEPT <target> [FROM <source>] statement.

    `from_source` holds the raw FROM operand (an environment-name like DATE/
    TIME/DAY or a mnemonic-name) when present, verbatim and unvalidated.

    `branch_path` — see PerformStmt.
    """

    target: str
    from_source: str | None = None
    branch_path: list[BranchCond] = field(default_factory=list)


@dataclass
class DisplayStmt:
    """A DISPLAY <item1> [<item2> ...] statement. `items` keeps identifiers
    and quoted literals as written, in order.

    `branch_path` — see PerformStmt.
    """

    items: list[str] = field(default_factory=list)
    branch_path: list[BranchCond] = field(default_factory=list)


@dataclass
class FileDescriptor:
    """A file declared via ENVIRONMENT DIVISION's FILE-CONTROL SELECT clause,
    merged with its DATA DIVISION FILE SECTION FD entry (matched by file-
    name). `organization`/`access_mode` are raw words from ORGANIZATION IS/
    ACCESS MODE IS (e.g. "INDEXED", "SEQUENTIAL", "DYNAMIC") — VSAM files are
    "INDEXED" (KSDS) or "RELATIVE" (RRDS); plain QSAM files are typically
    "SEQUENTIAL" or unspecified. `record_names` lists the 01/77-level record
    names declared under this file's FD (a file can have more than one, for
    redefinition purposes).
    """

    name: str
    organization: str | None = None
    access_mode: str | None = None
    record_key: str | None = None
    alternate_record_keys: list[str] = field(default_factory=list)
    file_status: str | None = None
    record_names: list[str] = field(default_factory=list)


@dataclass
class Paragraph:
    name: str
    section: str | None = None
    performs: list[PerformStmt] = field(default_factory=list)
    calls: list[CallStmt] = field(default_factory=list)
    go_tos: list[GoToStmt] = field(default_factory=list)
    io_statements: list[IoStmt] = field(default_factory=list)
    moves: list[MoveStmt] = field(default_factory=list)
    arithmetic: list[ArithmeticStmt] = field(default_factory=list)
    accepts: list[AcceptStmt] = field(default_factory=list)
    displays: list[DisplayStmt] = field(default_factory=list)


@dataclass
class ProcedureDivision:
    program_id: str | None
    sections: list[str]
    paragraphs: list[Paragraph]
    files: list[FileDescriptor] = field(default_factory=list)
