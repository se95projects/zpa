"""zpa — Python port of the Z PL/SQL Analyzer, starting with the lexer.

First unit of work: the lexer (string -> token stream). Everything downstream
(parser, AST walker, symbol table, checks) builds on this.
"""
from __future__ import annotations

from .lexer import LexError, PlSqlLexer, lex
from .tokens import EOF, IDENTIFIER, Token

__all__ = ["PlSqlLexer", "LexError", "lex", "Token", "IDENTIFIER", "EOF"]