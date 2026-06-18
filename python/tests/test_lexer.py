"""Unit tests for the lexer — a starting subset.

These are hand-written sanity checks. The authoritative correctness check is the
parity test (test_parity.py), which diffs against golden output emitted by the
Kotlin TokenOracleTest.
"""
from __future__ import annotations

from zpa import lex
from zpa.tokens import EOF


def categories(sql: str) -> list[str]:
    return [t.category for t in lex(sql) if t.category != EOF]


def values(sql: str) -> list[str]:
    return [t.value for t in lex(sql) if t.category != EOF]


def test_select_star():
    assert categories("select * from emp;") == [
        "SELECT", "MULTIPLICATION", "FROM", "IDENTIFIER", "SEMICOLON",
    ]


def test_keyword_is_normalized_uppercase():
    # FLR caseSensitive=false: keyword/identifier `value` is normalized.
    assert values("Select") == ["SELECT"]


def test_integer_vs_number():
    # plain integer -> INTEGER_LITERAL; float forms -> NUMBER_LITERAL
    assert categories("1") == ["INTEGER_LITERAL"]
    assert categories("2.5") == ["NUMBER_LITERAL"]
    assert categories("3e4") == ["NUMBER_LITERAL"]


def test_string_with_escaped_quote():
    toks = [t for t in lex("'it''s here'") if t.category != EOF]
    assert len(toks) == 1
    assert toks[0].category == "STRING_LITERAL"
    assert toks[0].value == "'it''s here'"


def test_maximal_munch_assignment():
    assert categories("x := 1;") == [
        "IDENTIFIER", "ASSIGNMENT", "INTEGER_LITERAL", "SEMICOLON",
    ]


def test_line_and_column_tracking():
    toks = lex("a\n  b")
    a = toks[0]
    b = toks[1]
    assert (a.line, a.column) == (1, 0)
    assert (b.line, b.column) == (2, 2)


def test_comments_are_trivia():
    assert categories("select -- comment\n1 from dual;") == [
        "SELECT", "INTEGER_LITERAL", "FROM", "IDENTIFIER", "SEMICOLON",
    ]
