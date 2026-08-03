from __future__ import annotations

from .models import ProcedureDivision


def build_flow_graph(proc: ProcedureDivision) -> list[tuple[str, str]]:
    """Build (caller_paragraph, performed_paragraph) edges from PERFORM statements.

    PERFORM <a> THRU <b> expands to edges into every paragraph physically
    between <a> and <b> (inclusive), matching COBOL's THRU semantics.
    """
    order = [p.name for p in proc.paragraphs]
    index = {name: i for i, name in enumerate(order)}

    edges: list[tuple[str, str]] = []
    for para in proc.paragraphs:
        for perform in para.performs:
            if perform.thru and perform.target in index and perform.thru in index:
                start, end = index[perform.target], index[perform.thru]
                if start > end:
                    start, end = end, start
                for target in order[start : end + 1]:
                    edges.append((para.name, target))
            else:
                edges.append((para.name, perform.target))

    return edges
