from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PerformStmt:
    """A PERFORM <target> [THRU <thru>] [VARYING <varying>] [UNTIL ...] statement.

    `until` only records whether an UNTIL clause is present (a looping
    PERFORM) — the condition expression itself isn't parsed, since that
    requires full COBOL expression grammar, out of scope for this tool.
    """

    target: str
    thru: str | None = None
    varying: str | None = None
    until: bool = False


@dataclass
class CallStmt:
    """A CALL statement. `dynamic` is True when the target is an identifier
    (resolved at runtime) rather than a literal program-name. `using` lists
    argument identifiers (BY REFERENCE/CONTENT/VALUE qualifiers stripped)."""

    target: str
    dynamic: bool = False
    using: list[str] = field(default_factory=list)
    returning: str | None = None


@dataclass
class GoToStmt:
    """A GO TO <target> statement.

    Only the single-target form is recognized — the older
    'GO TO a b c DEPENDING ON x' multi-target form is not supported.
    """

    target: str


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
