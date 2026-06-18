"""Lexer parity test — the authoritative correctness check.

Diffs the Python lexer's output against golden token lists emitted by the Kotlin
`TokenOracleTest`. Both sides tokenize the SAME corpus (parity/corpus.json) and
must produce the same `(category, value, line, column)` sequence.

Workflow:
  1. (Kotlin) point TokenOracleTest at parity/corpus.json and run:
         ./gradlew :zpa-core:test --tests "*TokenOracleTest*" --rerun-tasks
     -> writes zpa-core/build/goldens/tokens/<name>.json
  2. (Python) run pytest; this test writes its own tokenization to
         python/build/tokens/<name>.json
     and compares it against each golden. Diff the two trees directly with:
         diff -ru zpa-core/build/goldens/tokens python/build/tokens

If goldens are absent (oracle not run yet), the comparison is skipped with a hint
rather than failing — but the Python JSON is still written, so the scaffold is
green and you have output to inspect before the oracle exists.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from zpa import lex
from zpa.tokens import EOF

HERE = Path(__file__).resolve().parent
PY_ROOT = HERE.parent
REPO = PY_ROOT.parent
CORPUS = PY_ROOT / "parity" / "corpus.json"
GOLDEN_DIR = REPO / "zpa-core" / "build" / "goldens" / "tokens"   # Kotlin output
PY_OUT_DIR = PY_ROOT / "build" / "tokens"                         # Python output


def _load_corpus() -> dict[str, str]:
    data = json.loads(CORPUS.read_text())
    return data["cases"]


CASES = _load_corpus()


@pytest.mark.parametrize("name", sorted(CASES))
def test_token_parity(name: str):
    actual = [t.as_dict() for t in lex(CASES[name]) if t.category != EOF]

    # Always dump the Python output so it can be diffed against the Kotlin goldens,
    # even before the oracle has run. Mirrors the goldens' layout/formatting:
    #   diff -ru zpa-core/build/goldens/tokens python/build/tokens
    PY_OUT_DIR.mkdir(parents=True, exist_ok=True)
    (PY_OUT_DIR / f"{name}.json").write_text(json.dumps(actual, indent=2) + "\n")

    golden_file = GOLDEN_DIR / f"{name}.json"
    if not golden_file.exists():
        pytest.skip(
            f"golden {golden_file.relative_to(REPO)} not found — run the Kotlin "
            f"TokenOracleTest first (see this file's docstring). Python output was "
            f"still written to {(PY_OUT_DIR / f'{name}.json').relative_to(REPO)}."
        )

    expected = json.loads(golden_file.read_text())
    assert actual == expected, _diff(name, expected, actual)


def _diff(name: str, expected: list[dict], actual: list[dict]) -> str:
    lines = [f"token mismatch for case '{name}':"]
    for i in range(max(len(expected), len(actual))):
        e = expected[i] if i < len(expected) else None
        a = actual[i] if i < len(actual) else None
        flag = "" if e == a else "  <-- differs"
        lines.append(f"  [{i}] expected={e} actual={a}{flag}")
    return "\n".join(lines)