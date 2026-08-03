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

    Only the single-target form is recognized — the older
    'GO TO a b c DEPENDING ON x' multi-target form is not supported.

    `branch_path` — see PerformStmt.
    """

    target: str
    branch_path: list[BranchCond] = field(default_factory=list)


@dataclass
class Paragraph:
    name: str
    section: str | None = None
    performs: list[PerformStmt] = field(default_factory=list)
    calls: list[CallStmt] = field(default_factory=list)
    go_tos: list[GoToStmt] = field(default_factory=list)


@dataclass
class ProcedureDivision:
    program_id: str | None
    sections: list[str]
    paragraphs: list[Paragraph]
