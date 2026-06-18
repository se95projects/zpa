"""Regexes carried over verbatim from `zpa-core`'s PlSqlLexer.kt.

These are transcribed from the Kotlin source so they can be diffed against it.
Python 3.11+ supports possessive quantifiers (`++`, `*+`) and the `regex` module
supports `\\p{L}`, so the patterns port almost unchanged.

Confidence levels (the parity oracle is the final arbiter — see python/README.md):
  - SOLID:   COMMENT, INTEGER, IDENTIFIER, QUOTED_IDENTIFIER, DATE, TIMESTAMP
  - VERIFY:  NUMBER (float forms), STRING (custom q'' delimiters) — exercise these
             against the oracle corpus before trusting them.
"""
from __future__ import annotations

import regex  # third-party; supports \p{L}

# --- comments (consumed as trivia, emit no token) ---
INLINE_COMMENT = r"--[^\n\r]*+"
MULTILINE_COMMENT = r"/\*[\s\S]*?\*/"
COMMENT = regex.compile(rf"(?:{INLINE_COMMENT}|{MULTILINE_COMMENT})")

# --- numeric / integer ---
# NUMBER only matches *float-ish* forms (requires a '.', an exponent, or an f/d
# suffix); plain integer runs fall through to the integer channel by design.
NUMBER = regex.compile(
    r"(?is)(?:"
    r"(?:(?:\d++(?![.][.])[.]\d*+)|(?![.][.])[.]\d++)(?:e[+-]?\d++)?[fd]?"
    r"|\d++(?:e[+-]?\d++)?[fd]"
    r"|\d++(?:e[+-]?\d++)"
    r")"
)
INTEGER = regex.compile(r"\d+")

# --- string literals ---
# Simple form: '...'/''-escaped, optional n prefix. SOLID.
STRING_SIMPLE = r"n?'(?:[^']|'')*+'"
# TODO(VERIFY): user-defined-delimiter q-quotes, e.g.  q'[ ... ]'  n q'{ ... }'.
# Carried over from PlSqlLexer.STRING_LITERAL; confirm the \1 backreference form
# against the oracle before relying on it.
STRING_QQUOTE = (
    r"n?q?'(?:"
    r"(?:([^\s{\[<\(]).*?\1')"   # custom single-char delimiter
    r"|(?:\(.*?\)')"
    r"|(?:\[.*?\]')"
    r"|(?:<.*?>')"
    r"|(?:\{.*?\}')"
    r")"
)
STRING = regex.compile(rf"(?is)(?:{STRING_SIMPLE}|{STRING_QQUOTE})")

# --- date / timestamp literals ---
DATE = regex.compile(r"(?i)(?:DATE\s*?'\d{4}-\d{2}-\d{2}')")
TIMESTAMP = regex.compile(
    r"(?i)TIMESTAMP\s*?'\d{4}-\d{2}-\d{2}\s++\d{1,2}:\d{2}:\d{2}"
    r"(?:.\d{1,9})?(?:\s++[A-Z0-9_/+\-:]++(?:\s++[A-Z0-9_/+\-]{1,5})?)?'"
)

# --- identifiers ---
SIMPLE_IDENTIFIER = regex.compile(r"[\w\p{L}][\w\p{L}#$]*+")
QUOTED_IDENTIFIER = regex.compile(r'".+?"')

# --- blackhole: conditional-compilation directives + `&&substitution` (consumed,
# no token). Carried over from PlSqlLexer's BlackHoleChannel. ---
_IDENT = r"[\w\p{L}][\w\p{L}#$]*"
BLACKHOLE = regex.compile(
    r"(?is)(?:"
    rf"\s&&?{_IDENT}"
    r"|\$if.*?\$then"
    r"|\$else.*?\$end"
    r"|\$error.*?\$end"
    r"|\$end"
    r")"
)
