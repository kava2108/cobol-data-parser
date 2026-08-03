from __future__ import annotations

from dataclasses import dataclass, field

from .models import BranchCond, ProcedureDivision


@dataclass
class FileAccessEdge:
    """One paragraph's access to one file, from a READ/WRITE/REWRITE/DELETE/
    START statement. `file_name` is the resolved file-name: for READ/DELETE/
    START this is the IoStmt's target as-is (already a file-name); for
    WRITE/REWRITE it's resolved from the record-name via the owning FD's
    record_names (see build_file_access_graph()) — or, if that lookup fails
    or is ambiguous, "UNRESOLVED:<record-name>" (same convention
    build_call_graph() uses for dynamic CALL targets it can't resolve
    statically)."""

    paragraph: str
    file_name: str
    operation: str
    branch_path: list[BranchCond] = field(default_factory=list)


def _record_to_file_map(proc: ProcedureDivision) -> dict[str, str]:
    """Map each record-name to its owning file-name, dropping any record-name
    claimed by more than one FD — silently picking one of two colliding FDs
    would be a worse outcome than leaving it unresolved."""
    record_to_file: dict[str, str] = {}
    ambiguous: set[str] = set()

    for fd in proc.files:
        for record_name in fd.record_names:
            if record_name in record_to_file and record_to_file[record_name] != fd.name:
                ambiguous.add(record_name)
            else:
                record_to_file[record_name] = fd.name

    for record_name in ambiguous:
        del record_to_file[record_name]

    return record_to_file


def build_file_access_graph(proc: ProcedureDivision) -> list[FileAccessEdge]:
    """Build (paragraph, file) edges from READ/WRITE/REWRITE/DELETE/START
    statements, each tagged with the IF/EVALUATE branch (if any) it's nested
    under — see IoStmt.branch_path.

    READ/DELETE/START already target a file-name directly. WRITE/REWRITE
    target a record-name in COBOL source, resolved back to a file-name via
    the FileDescriptor.record_names collected from FILE SECTION FD entries
    (see environment.py); unresolvable or ambiguous record-names fall back
    to "UNRESOLVED:<record-name>".
    """
    record_to_file = _record_to_file_map(proc)

    edges: list[FileAccessEdge] = []
    for para in proc.paragraphs:
        for io in para.io_statements:
            if io.operation in ("WRITE", "REWRITE"):
                file_name = record_to_file.get(io.target, f"UNRESOLVED:{io.target}")
            else:
                file_name = io.target
            edges.append(FileAccessEdge(para.name, file_name, io.operation, io.branch_path))

    return edges
