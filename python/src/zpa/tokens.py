"""Token model — the lexer's output contract.

`category` mirrors the Kotlin `TokenType.name` so output is directly comparable
against the parity oracle (see python/README.md). Examples:
  - keywords  -> the enum constant name, e.g. "SELECT"
  - operators -> the punctuator name, e.g. "MULTIPLICATION"
  - literals  -> one of token_types.LITERAL_TYPES, e.g. "INTEGER_LITERAL"
  - bare names -> "IDENTIFIER"
  - end of input -> "EOF"
"""
from __future__ import annotations

from dataclasses import dataclass

IDENTIFIER = "IDENTIFIER"
EOF = "EOF"


@dataclass(frozen=True, slots=True)
class Token:
    category: str
    value: str
    line: int        # 1-based  (FLR convention)
    column: int      # 0-based  (FLR convention)

    def as_dict(self) -> dict:
        """Shape used by the parity harness to diff against the Kotlin oracle."""
        return {
            "category": self.category,
            "value": self.value,
            "line": self.line,
            "column": self.column,
        }
