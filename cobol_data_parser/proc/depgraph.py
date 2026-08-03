from __future__ import annotations

from .models import ProcedureDivision


def build_call_graph(proc: ProcedureDivision) -> list[tuple[str, str]]:
    """Build (program_id, called_target) edges from CALL statements.

    Dynamic CALLs (identifier targets, resolved at runtime) are prefixed
    with 'DYNAMIC:' since the actual called program cannot be known statically.
    """
    caller = proc.program_id or "UNKNOWN"
    edges: list[tuple[str, str]] = []
    for para in proc.paragraphs:
        for call in para.calls:
            target = f"DYNAMIC:{call.target}" if call.dynamic else call.target
            edges.append((caller, target))
    return edges
