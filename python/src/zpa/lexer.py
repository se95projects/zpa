"""PlSqlLexer — wires the channels in priority order and drives the scan.

Channel order is copied verbatim from `PlSqlLexer.create()` in zpa-core. The
driver tries each channel at the cursor; the first to consume >=1 character wins.
This mirrors FLR's `withFailIfNoChannelToConsumeOneCharacter(true)` — except the
trailing UnknownCharacterChannel always consumes one char, so the scan can't stall.
"""
from __future__ import annotations

from . import patterns, token_types
from .channels import (
    BlackHoleChannel,
    Channel,
    CommentChannel,
    DateChannel,
    IdentifierKeywordChannel,
    IntegerChannel,
    NumericChannel,
    PunctuatorChannel,
    QuotedIdentifierChannel,
    StringChannel,
    UnknownCharacterChannel,
    WhitespaceChannel,
)
from .reader import CodeReader
from .tokens import EOF, Token


def _channels() -> list[Channel]:
    # Order matters — identical to PlSqlLexer.create().
    return [
        WhitespaceChannel(),
        CommentChannel(),
        NumericChannel(),
        IntegerChannel(),
        StringChannel(),
        DateChannel(token_types.DATE_LITERAL, patterns.DATE),
        DateChannel(token_types.TIMESTAMP_LITERAL, patterns.TIMESTAMP),
        IdentifierKeywordChannel(),
        QuotedIdentifierChannel(),
        PunctuatorChannel(),
        BlackHoleChannel(),
        UnknownCharacterChannel(),
    ]


class PlSqlLexer:
    def __init__(self) -> None:
        self._channels = _channels()

    def lex(self, source: str) -> list[Token]:
        reader = CodeReader(source)
        tokens: list[Token] = []
        while not reader.eof:
            for channel in self._channels:
                if channel.consume(reader, tokens):
                    break
            else:  # pragma: no cover - UnknownCharacterChannel is total
                raise LexError(
                    f"no channel consumed input at line {reader.line}, "
                    f"column {reader.column}: {reader.peek()!r}"
                )
        tokens.append(Token(EOF, "EOF", reader.line, reader.column))
        return tokens


class LexError(Exception):
    pass


def lex(source: str) -> list[Token]:
    """Convenience: tokenize `source` with a fresh lexer."""
    return PlSqlLexer().lex(source)