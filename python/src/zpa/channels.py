"""Channels — one per token shape, tried in order by the lexer driver.

Each channel mirrors a `*Channel.kt` in zpa-core. A channel's `consume` either:
  - matches at the cursor, appends zero or more tokens, advances the reader,
    and returns True; or
  - returns False without touching the reader.

The cheap first-character guards (e.g. "comments start with - or /") are copied
from the Kotlin channels: they're an optimization, not correctness, but kept for
fidelity and to make the ordering obvious.
"""
from __future__ import annotations

from typing import Protocol

from . import patterns, token_types
from .keywords import KEYWORD_BY_LEXEME
from .punctuators import PUNCTUATORS
from .reader import CodeReader
from .tokens import IDENTIFIER, Token


class Channel(Protocol):
    def consume(self, reader: CodeReader, sink: list[Token]) -> bool: ...


class WhitespaceChannel:
    """DiscardWhitespaceChannel — drops whitespace, except a '&' sentinel (handled
    by the blackhole channel for conditional-compilation `&&` constructs)."""

    def consume(self, reader: CodeReader, sink: list[Token]) -> bool:
        ch = reader.peek()
        if ch and ch.isspace() and reader.peek(1) != "&":
            reader.pop()
            return True
        return False


class CommentChannel:
    """CommentChannel — line (`--`) and block (`/* */`) comments. Comments are
    trivia in ZPA: consumed but not emitted into the token stream."""

    def consume(self, reader: CodeReader, sink: list[Token]) -> bool:
        if reader.peek() not in ("-", "/"):
            return False
        return reader.match(patterns.COMMENT) is not None


class _RegexLiteralChannel:
    """Base for channels that match a regex and emit a single literal token."""

    category: str
    pattern = None  # type: ignore[assignment]
    guard: tuple[str, ...] = ()

    def consume(self, reader: CodeReader, sink: list[Token]) -> bool:
        if self.guard and reader.peek().lower() not in self.guard:
            return False
        text = reader.match(self.pattern)
        if text is None:
            return False
        sink.append(Token(self.category, text, reader.prev_line, reader.prev_column))
        return True


class NumericChannel(_RegexLiteralChannel):
    category = token_types.NUMBER_LITERAL
    pattern = patterns.NUMBER

    def consume(self, reader: CodeReader, sink: list[Token]) -> bool:
        ch = reader.peek()
        if not (ch.isdigit() or ch == "."):
            return False
        return super().consume(reader, sink)


class IntegerChannel(_RegexLiteralChannel):
    category = token_types.INTEGER_LITERAL
    pattern = patterns.INTEGER

    def consume(self, reader: CodeReader, sink: list[Token]) -> bool:
        if not reader.peek().isdigit():
            return False
        return super().consume(reader, sink)


class StringChannel(_RegexLiteralChannel):
    category = token_types.STRING_LITERAL
    pattern = patterns.STRING
    guard = ("'", "n", "q")


class DateChannel(_RegexLiteralChannel):
    """DateChannel handles both DATE '...' and TIMESTAMP '...' (two instances in
    Kotlin, distinguished here by category + pattern)."""

    def __init__(self, category: str, pattern) -> None:
        self.category = category
        self.pattern = pattern
        self.guard = ("d", "t")


class IdentifierKeywordChannel:
    """IdentifierChannel + IdentifierAndKeywordChannel — match an identifier, then
    classify it as a reserved/non-reserved keyword (by lowercased lexeme) or a
    plain IDENTIFIER.

    NOTE(VERIFY): FLR runs with caseSensitive=false, so the token `value` is
    NORMALIZED (keyword lexeme / upper-cased identifier) while the as-typed text is
    kept as originalValue. ZPA's checks read `tokenOriginalValue` for real names.
    The parity oracle compares `.value`, so we store the normalized form here.
    Confirm the exact normalization (upper vs lexeme-case) against the oracle.
    """

    def consume(self, reader: CodeReader, sink: list[Token]) -> bool:
        if not reader.peek().isalpha():
            return False
        text = reader.match(patterns.SIMPLE_IDENTIFIER)
        if text is None:
            return False
        category = KEYWORD_BY_LEXEME.get(text.lower(), IDENTIFIER)
        value = text.upper()  # FLR caseSensitive=false normalization — see NOTE
        sink.append(Token(category, value, reader.prev_line, reader.prev_column))
        return True


class QuotedIdentifierChannel:
    """QuotedIdentifierChannel — `"quoted"` identifiers. An all-uppercase quoted
    name that is otherwise a simple identifier has its quotes stripped (matching
    Kotlin); anything else keeps the quotes."""

    _simple_quoted = patterns.regex.compile(rf'"{patterns.SIMPLE_IDENTIFIER.pattern}"')

    def consume(self, reader: CodeReader, sink: list[Token]) -> bool:
        if reader.peek() != '"':
            return False
        text = reader.match(patterns.QUOTED_IDENTIFIER)
        if text is None:
            return False
        value = text
        if self._simple_quoted.fullmatch(text) and text == text.upper():
            value = text[1:-1]
        sink.append(Token(IDENTIFIER, value, reader.prev_line, reader.prev_column))
        return True


class PunctuatorChannel:
    """PunctuatorChannel — operators and separators, maximal munch (PUNCTUATORS is
    pre-sorted longest-first)."""

    def consume(self, reader: CodeReader, sink: list[Token]) -> bool:
        for category, lexeme in PUNCTUATORS:
            if _starts_with(reader, lexeme):
                line, col = reader.line, reader.column
                for _ in lexeme:
                    reader.pop()
                sink.append(Token(category, lexeme, line, col))
                return True
        return False


class BlackHoleChannel:
    """BlackHoleChannel — conditional-compilation directives ($if/$then/$end) and
    `&&substitution` variables. Consumed and discarded (no token)."""

    def consume(self, reader: CodeReader, sink: list[Token]) -> bool:
        ch = reader.peek()
        if ch not in ("$", " ", "\t", "\n", "\r"):
            return False
        return reader.match(patterns.BLACKHOLE) is not None


class UnknownCharacterChannel:
    """UnknownCharacterChannel — final fallback; consumes exactly one character so
    the driver never stalls. Emitted as UNKNOWN_CHAR for parity visibility."""

    def consume(self, reader: CodeReader, sink: list[Token]) -> bool:
        if reader.eof:
            return False
        line, col = reader.line, reader.column
        sink.append(Token("UNKNOWN_CHAR", reader.pop(), line, col))
        return True


def _starts_with(reader: CodeReader, lexeme: str) -> bool:
    return all(reader.peek(i) == ch for i, ch in enumerate(lexeme))
