# zpa (Python port)

A ground-up Python port of the [Z PL/SQL Analyzer](../README.md), built
bottom-up. **First unit of work: the lexer** — `string -> token stream`. It's the
only piece with no downstream dependencies; the parser, AST walker, symbol table,
and checks all build on top of it.

## Layout

```
python/
├── pyproject.toml             # package + pytest config (src layout)
├── parity/
│   └── corpus.json            # shared lexer corpus — single source of truth for
│                              #   BOTH the Python test and the Kotlin oracle
├── sql/                       # sample fixtures (low/medium/high complexity)
├── src/zpa/
│   ├── tokens.py              # Token dataclass — the output contract
│   ├── reader.py              # CodeReader: cursor + line/col tracking (the only
│   │                          #   bit of FLR framework Python lacks)
│   ├── channels.py            # one channel per token shape (mirrors *Channel.kt)
│   ├── lexer.py               # PlSqlLexer: wires channels in order, drives scan
│   ├── patterns.py            # regexes carried over from PlSqlLexer.kt
│   ├── keywords.py            # AUTO-GENERATED keyword table (575 entries)
│   ├── punctuators.py         # AUTO-GENERATED punctuator table (maximal-munch order)
│   └── token_types.py         # AUTO-GENERATED literal categories
├── tests/
│   ├── test_lexer.py          # hand-written sanity checks
│   └── test_parity.py         # authoritative: dump + diff vs Kotlin golden output
└── tools/
    └── generate_token_tables.py   # regenerates the AUTO-GENERATED data files
```

## Setup & run

```bash
cd python
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # runs unit + parity tests
```

The `regex` dependency (not stdlib `re`) is required for `\p{L}` Unicode property
support in the identifier patterns.

## Regenerating the data tables

`keywords.py`, `punctuators.py`, and `token_types.py` are transcribed from the
Kotlin enums in `zpa-core`. Never edit them by hand — re-derive from upstream:

```bash
python tools/generate_token_tables.py
```

## Correctness: parity against the Kotlin lexer

Rather than assert against hand-written expectations, the Python lexer is diffed
against **golden output emitted by the Kotlin lexer** over a shared corpus. Both
sides tokenize `parity/corpus.json` and must produce the same
`(category, value, line, column)` sequence. The full oracle design (lexer, parser,
checks, metrics) is documented in [Parity_Tests.md](Parity_Tests.md).

```
parity/corpus.json
   │
   ├──> Kotlin TokenOracleTest ──> zpa-core/build/goldens/tokens/<name>.json
   │
   └──> Python lex()           ──> python/build/tokens/<name>.json
                                       │
                                  test_parity.py compares the two
```

Generate both trees, then diff them directly:

```bash
# from repo root — Kotlin goldens
./gradlew :zpa-core:test --tests "*TokenOracleTest*" --rerun-tasks

# from python/ — Python output (also runs the structural comparison)
pytest tests/test_parity.py

# quick structural pass/fail per case (ignores JSON formatting)
python tools/diff_tokens.py

# or eyeball the raw difference, file-for-file
diff -ru zpa-core/build/goldens/tokens python/build/tokens
```

`tools/diff_tokens.py` loads each Python dump and its matching Kotlin golden,
compares them structurally, and prints `<name> --> True|False` (skipping cases
with no golden yet).

`test_parity.py` always writes `python/build/tokens/<name>.json` first, so you get
inspectable output even before the goldens exist (the comparison is skipped, not
failed, when a golden is missing).

### Normalization both sides must agree on

- **category** = the Kotlin `TokenType.name` (`"SELECT"`, `"IDENTIFIER"`,
  `"MULTIPLICATION"`, `"INTEGER_LITERAL"`, …).
- **line** is 1-based; **column** is 0-based (FLR convention).
- The trailing **EOF** token is dropped before comparing.
- Keyword/identifier **value** is normalized (upper-cased) because FLR runs
  `caseSensitive = false`; as-typed text is the *original value* (not compared here).

## Status / what's left in this unit

| Piece | State |
|---|---|
| Token model, CodeReader, driver, channel wiring | done |
| Data tables (keywords, punctuators, literals) | done (generated) |
| Whitespace, comment, integer, punctuator, identifier/keyword, quoted-id channels | first pass |
| Number (float forms), string (`q'[]'` custom delimiters), date/timestamp | carried over — **VERIFY against oracle** |
| Parity harness (dump + compare) | done; needs goldens generated |

The `VERIFY` items have their regexes transcribed but the tricky cases (custom
`q''` delimiters, float edge cases) should be confirmed against the oracle corpus
before being trusted. Grow `parity/corpus.json` to pin them down.
