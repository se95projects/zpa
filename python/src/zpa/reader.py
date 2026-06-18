"""CodeReader — the small framework piece FLR provides that Python lacks.

Wraps the source string with a cursor that tracks 1-based line and 0-based column
(FLR convention), and lets channels (a) peek at upcoming characters and (b) match a
compiled regex anchored at the cursor. This is the only non-mechanical part of the
lexer port; everything else is regex + data.
"""
from __future__ import annotations

import re


class CodeReader:
    def __init__(self, text: str) -> None:
        self._text = text
        self._pos = 0
        self._line = 1
        self._column = 0
        # cursor (line, column) captured at the start of the most recent match,
        # mirroring FLR's CodeReader.previousCursor.
        self.prev_line = 1
        self.prev_column = 0

    @property
    def eof(self) -> bool:
        return self._pos >= len(self._text)

    @property
    def line(self) -> int:
        return self._line

    @property
    def column(self) -> int:
        return self._column

    def peek(self, offset: int = 0) -> str:
        """Character at cursor+offset, or '' past end of input."""
        i = self._pos + offset
        return self._text[i] if i < len(self._text) else ""

    def _advance(self, n: int) -> str:
        """Consume n characters, updating line/column. Returns the consumed text."""
        chunk = self._text[self._pos : self._pos + n]
        for ch in chunk:
            if ch == "\n":
                self._line += 1
                self._column = 0
            else:
                self._column += 1
        self._pos += n
        return chunk

    def pop(self) -> str:
        """Consume and return a single character."""
        return self._advance(1)

    def match(self, pattern: re.Pattern[str]) -> str | None:
        """If `pattern` matches anchored at the cursor, record the start cursor in
        prev_line/prev_column, consume the match, and return the matched text.
        Otherwise leave the cursor untouched and return None."""
        m = pattern.match(self._text, self._pos)
        if not m or m.end() == m.start():
            return None
        self.prev_line, self.prev_column = self._line, self._column
        return self._advance(m.end() - m.start())