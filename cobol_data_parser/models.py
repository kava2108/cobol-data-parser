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


@dataclass
class DataItem:
    level: int
    name: str
    pic: Optional[PicClause] = None
    usage: Optional[str] = None
    redefines: Optional[str] = None
    occurs: Optional[int] = None
    children: list[DataItem] = field(default_factory=list)

    @property
    def is_group(self) -> bool:
        # 88-level (condition names) and 66-level (RENAMES) don't make a group
        return any(c.level not in (66, 88) for c in self.children)

    @property
    def is_filler(self) -> bool:
        return self.name.upper() == "FILLER"
