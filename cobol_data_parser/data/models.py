from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PicCategory(str, Enum):
    STRING = "string"
    ALPHABETIC = "alphabetic"
    NUMERIC = "numeric"
    SIGNED_NUMERIC = "signed-numeric"
    DECIMAL = "decimal"
    SIGNED_DECIMAL = "signed-decimal"
    NUMERIC_EDITED = "numeric-edited"
    ALPHANUMERIC_EDITED = "alphanumeric-edited"
    BINARY = "binary"
    PACKED_DECIMAL = "packed-decimal"


@dataclass
class PicClause:
    raw: str
    category: PicCategory
    length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    edit_symbols: Optional[list[str]] = None


@dataclass
class OccursClause:
    """Represents an OCCURS clause — fixed or variable-length (ODO)."""
    min_occurs: int
    max_occurs: int
    depending_on: Optional[str] = None  # None for fixed OCCURS

    @property
    def is_variable(self) -> bool:
        return self.depending_on is not None

    @classmethod
    def fixed(cls, count: int) -> OccursClause:
        return cls(min_occurs=count, max_occurs=count)

    @classmethod
    def variable(cls, min_count: int, max_count: int, depending_on: str) -> OccursClause:
        return cls(min_occurs=min_count, max_occurs=max_count, depending_on=depending_on)


@dataclass
class DataItem:
    level: int
    name: str
    pic: Optional[PicClause] = None
    usage: Optional[str] = None
    redefines: Optional[str] = None
    occurs: Optional[OccursClause] = None
    byte_length: Optional[int] = None
    offset: Optional[int] = None
    sign_separate: bool = False
    sign_leading: bool = False
    renames: Optional[str] = None
    renames_thru: Optional[str] = None
    children: list[DataItem] = field(default_factory=list)

    @property
    def is_group(self) -> bool:
        # 88-level (condition names) and 66-level (RENAMES) don't make a group
        return any(c.level not in (66, 88) for c in self.children)

    @property
    def is_filler(self) -> bool:
        return self.name.upper() == "FILLER"
