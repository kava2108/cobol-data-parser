from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PerformStmt:
    """A PERFORM <target> [THRU <thru>] statement."""

    target: str
    thru: str | None = None


@dataclass
class CallStmt:
    """A CALL statement. `dynamic` is True when the target is an identifier
    (resolved at runtime) rather than a literal program-name."""

    target: str
    dynamic: bool = False


@dataclass
class Paragraph:
    name: str
    section: str | None = None
    performs: list[PerformStmt] = field(default_factory=list)
    calls: list[CallStmt] = field(default_factory=list)


@dataclass
class ProcedureDivision:
    program_id: str | None
    sections: list[str]
    paragraphs: list[Paragraph]
