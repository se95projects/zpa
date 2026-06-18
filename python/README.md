# ZPA → Python Parity Oracles

Four Kotlin tests that emit **implementation-independent** golden output. Your Python
port reproduces the same output and you diff the two. All APIs below are verified against
FLR 1.5.0 / ZPA `main` source.

## What is and isn't comparable

| Layer | Compare on | Why it works |
|---|---|---|
| Lexer | `(category, value, line, column)` per token | both lexers tokenize the same language |
| Parser | `PASS / FAIL` per input string | accept/reject is a boolean, grammar-shape-independent |
| Checks | `(rule, startLine, startCol, endLine, endCol, message)` per issue | end-user-visible output |
| Metrics | size + complexity scalars per file | numbers, fully comparable — *if* increment rules match |

**Do NOT diff parse trees.** FLR's AST node names and nesting (the
`OR_EXPRESSION → AND_EXPRESSION → …` wrapper tower, etc.) are specific to its grammar.
Your Python parser produces a different tree shape and will never diff equal — that's
expected, not a bug. Compare the four normalized contracts above instead.

### Normalization rules (both sides must follow)

- **category** = the token type's `name` (e.g. `"SELECT"`, `"IDENTIFIER"`, `"MUL"`).
  Map your Python token kinds onto these same strings.
- **column** is **0-based** (FLR convention). `line` is **1-based**.
- Drop the trailing **EOF** token.
- Issue offsets: `startLineOffset` / `endLineOffset` are 0-based columns;
  line-level issues report `UNDEFINED_OFFSET` (a sentinel int) — treat consistently.

---

## 1. Lexer oracle — `TokenOracleTest`

**Lives in:** `zpa-core/src/test/kotlin/com/felipebz/zpa/oracle/`
(only needs the lexer, which is in zpa-core)

**Run:**
```bash
./gradlew :zpa-core:test --tests "*TokenOracleTest*" --rerun-tasks
```

**Emits:** `zpa-core/build/goldens/tokens/<name>.json` — commit these.

```kotlin
package com.felipebz.zpa.oracle

import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.SerializationFeature
import com.felipebz.flr.api.GenericTokenType
import com.felipebz.zpa.lexer.PlSqlLexer
import com.felipebz.zpa.squid.PlSqlConfiguration
import org.junit.jupiter.api.Test
import java.io.File
import java.nio.charset.StandardCharsets

class TokenOracleTest {

    /** The comparable contract. Python emits the same four fields. */
    data class Tok(val category: String, val value: String, val line: Int, val column: Int)

    private val mapper = ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT)

    private fun tokenize(sql: String): List<Tok> =
        PlSqlLexer.create(PlSqlConfiguration(StandardCharsets.UTF_8))
            .lex(sql)                                   // lex(String): List<Token>
            .asSequence()
            .filterNot { it.type == GenericTokenType.EOF }
            .map { Tok(it.type.name, it.value, it.line, it.column) }
            .toList()

    private fun dump(name: String, sql: String) {
        val dir = File("build/goldens/tokens").apply { mkdirs() }
        File(dir, "$name.json").writeText(mapper.writeValueAsString(tokenize(sql)))
    }

    @Test
    fun dumpCorpus() {
        dump("select_star", "select * from emp;")
        dump("select_into", "select id into v_id from emp where id = 1;")
        dump("string_escaped_quote", "select 'it''s here' from dual;")
        dump("numbers", "select 1, 2.5, 3e4, .7 from dual;")
        dump("compare_null", "begin if x = null then null; end if; end;")
        // extend as coverage grows
    }
}
```

**Python reproduces:** a tokenizer that, for each corpus string, produces the same JSON
list of `{category, value, line, column}`. Diff file-for-file.

---

## 2. Parser oracle — `AcceptRejectTest`

**Lives in:** `zpa-core/src/test/kotlin/com/felipebz/zpa/oracle/`
(only needs the parser)

**Run:**
```bash
./gradlew :zpa-core:test --tests "*AcceptRejectTest*" --rerun-tasks
```

**Emits:** `zpa-core/build/goldens/accept_reject.tsv` — one `PASS|FAIL <tab> sql` line each.

```kotlin
package com.felipebz.zpa.oracle

import com.felipebz.zpa.parser.PlSqlParser
import com.felipebz.zpa.squid.PlSqlConfiguration
import org.junit.jupiter.api.Test
import java.io.File
import java.nio.charset.StandardCharsets

class AcceptRejectTest {

    // error recovery OFF so a bad parse throws RecognitionException -> caught -> FAIL.
    private val parser =
        PlSqlParser.create(PlSqlConfiguration(StandardCharsets.UTF_8))

    private fun accepts(sql: String): Boolean =
        try { parser.parse(sql); true } catch (e: Exception) { false }

    @Test
    fun dumpAcceptReject() {
        // Keep should-parse and should-NOT-parse strings. Both impls must agree on every line.
        val corpus = listOf(
            "select 1 from dual;",
            "select * from emp where id = 1;",
            "begin null; end;",
            "create procedure p is begin null; end;",
            // intentionally invalid:
            "select from;",
            "begin if then end;",
        )
        val out = File("build/goldens").apply { mkdirs() }
        File(out, "accept_reject.tsv").writeText(
            corpus.joinToString("\n") { sql ->
                "${if (accepts(sql)) "PASS" else "FAIL"}\t$sql"
            }
        )
    }
}
```

**Python reproduces:** for each corpus string, does your parser consume it fully without
error → `PASS`, else `FAIL`. Diff the TSV. This is grammar-shape-independent: you are only
asserting the two grammars admit the same language, not that they build the same tree.

---

## 3. Check oracle — `IssueOracleTest`

**Lives in:** `zpa-checks/src/test/kotlin/com/felipebz/zpa/checks/`
(needs the checks from zpa-checks **and** the scanner from zpa-core; only the zpa-checks
test sourceset sees both)

**Run:**
```bash
./gradlew :zpa-checks:test --tests "*IssueOracleTest*" --rerun-tasks -i
```

**Emits:** `zpa-checks/build/goldens/issues/<fixture>.json`

```kotlin
package com.felipebz.zpa.checks

import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.SerializationFeature
import com.felipebz.zpa.api.PlSqlFile
import com.felipebz.zpa.squid.AstScanner
import org.junit.jupiter.api.Test
import java.io.File

class IssueOracleTest {

    /** The comparable contract. rule = check class simple name; Python names checks to match. */
    data class Issue(
        val rule: String,
        val startLine: Int,
        val startCol: Int,
        val endLine: Int,
        val endCol: Int,
        val message: String,
    )

    private val mapper = ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT)

    private fun fileFor(path: File) = object : PlSqlFile {
        override fun contents() = path.readText()
        override fun fileName() = path.name
        override fun path() = path.toPath()
        override fun type() = PlSqlFile.Type.MAIN
    }

    @Test
    fun dumpIssues() {
        val sqlFile = File("../python/sql/low_complexity.sql").canonicalFile
        check(sqlFile.exists()) { "fixture not found: $sqlFile" }

        val scanner = AstScanner(
            checks = listOf(
                SelectAllColumnsCheck(),
                InsertWithoutColumnsCheck(),
                ComparisonWithNullCheck(),
            ),
            formsMetadata = null,
            isErrorRecoveryEnabled = false,   // all-zero result + no issues => file did not parse
        )

        val result = scanner.scanFile(fileFor(sqlFile))

        val issues = result.issues.map { issue ->
            val loc = issue.primaryLocation                 // ZpaIssue.primaryLocation
            Issue(
                rule = issue.check::class.simpleName ?: "Unknown",
                startLine = loc.startLine(),
                startCol = loc.startLineOffset(),           // 0-based; UNDEFINED_OFFSET for line issues
                endLine = loc.endLine(),
                endCol = loc.endLineOffset(),
                message = loc.message(),
            )
        }.sortedWith(compareBy({ it.startLine }, { it.startCol }, { it.rule }))

        val dir = File("build/goldens/issues").apply { mkdirs() }
        File(dir, "${sqlFile.nameWithoutExtension}.json")
            .writeText(mapper.writeValueAsString(issues))
    }
}
```

**Python reproduces:** run your ported checks over the same fixture, emit the same sorted
list of `{rule, startLine, startCol, endLine, endCol, message}`. Diff the JSON.

> Note: the existing `-- Noncompliant {{msg}} [[sc=N;ec=M]]` annotations in ZPA's
> `.sql` test fixtures are *already* a language-independent issue oracle — for those files
> you may not need this test at all. Use `IssueOracleTest` for new SQL you haven't annotated.

---

## 4. Metrics oracle — `MetricsOracleTest`

**Lives in:** `zpa-core/src/test/kotlin/com/felipebz/zpa/oracle/` (only needs `AstScanner`;
no check classes referenced — `zpa-checks` works too if you want it beside the issue oracle)

**Run:**
```bash
./gradlew :zpa-core:test --tests "*MetricsOracleTest*" --rerun-tasks -i
```

**Emits:** `build/goldens/metrics/<fixture>.json` (and prints to console with `-i`).

The metrics visitors (`MetricsVisitor`, `ComplexityVisitor`, `FunctionComplexityVisitor`)
are added **inside** `scanFile` automatically, so `checks = emptyList()` still produces all
metrics.

```kotlin
package com.felipebz.zpa.oracle

import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.SerializationFeature
import com.felipebz.zpa.api.PlSqlFile
import com.felipebz.zpa.squid.AstScanner
import org.junit.jupiter.api.Test
import java.io.File

class MetricsOracleTest {

    /** Comparable contract — all scalars. Python emits the same fields. */
    data class Metrics(
        val linesOfCode: Int,
        val linesOfComments: Int,
        val numberOfStatements: Int,
        val complexity: Int,
        val numberOfFunctions: Int,
        val executableLines: List<Int>,   // sorted for deterministic diff
        val symbols: Int,
    )

    private val mapper = ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT)

    @Test
    fun dumpMetrics() {
        val sqlFile = File("../python/sql/low_complexity.sql").canonicalFile
        check(sqlFile.exists()) { "fixture not found: $sqlFile" }

        val plSqlFile = object : PlSqlFile {
            override fun contents() = sqlFile.readText()
            override fun fileName() = sqlFile.name
            override fun path() = sqlFile.toPath()
            override fun type() = PlSqlFile.Type.MAIN
        }

        val scanner = AstScanner(
            checks = emptyList(),
            formsMetadata = null,
            isErrorRecoveryEnabled = false,   // all-zero metrics => the file did not parse
        )

        val r = scanner.scanFile(plSqlFile)

        val metrics = Metrics(
            linesOfCode = r.linesOfCode,
            linesOfComments = r.linesOfComments,
            numberOfStatements = r.numberOfStatements,
            complexity = r.complexity,
            numberOfFunctions = r.numberOfFunctions,
            executableLines = r.executableLines.sorted(),
            symbols = r.symbols.size,
        )

        println("file               : $sqlFile")
        println("lines of code      : ${metrics.linesOfCode}")
        println("lines of comments  : ${metrics.linesOfComments}")
        println("statements         : ${metrics.numberOfStatements}")
        println("complexity (total) : ${metrics.complexity}")
        println("functions          : ${metrics.numberOfFunctions}")
        println("executable lines   : ${metrics.executableLines}")
        println("symbols            : ${metrics.symbols}")

        val dir = File("build/goldens/metrics").apply { mkdirs() }
        File(dir, "${sqlFile.nameWithoutExtension}.json")
            .writeText(mapper.writeValueAsString(metrics))
    }
}
```

**Python reproduces:** the same scalar metrics for the same fixture. Two caveats:

- `complexity` is the **file aggregate**. The result exposes the total and
  `numberOfFunctions` but **not** per-function complexity — that needs a custom visitor.
- The numbers only match if Python replicates ZPA's **exact** complexity increment rules
  (which AST nodes count as decision points). A diff here is usually a counting-rule
  mismatch, not a parser bug. ZPA's `ComplexityVisitor` is the source of truth.

---

## Diffing on the Python side

For JSON goldens, load both and compare structurally (don't string-compare formatted JSON):

```python
import json
def load(p):
    with open(p) as f: return json.load(f)
assert load("py_tokens.json") == load("kt_tokens/select_star.json")
```

For the accept/reject TSV, compare line sets (order doesn't matter if you sort both).

## API reference (verified)

| Symbol | Signature / location |
|---|---|
| `PlSqlLexer.create(conf)` | returns FLR `Lexer` |
| `Lexer.lex(String)` | `: List<Token>` |
| `Token` | `.type: TokenType`, `.value`, `.originalValue`, `.line` (1-based), `.column` (0-based) |
| `TokenType.name` | `: String` (property) |
| `GenericTokenType.EOF` | the EOF sentinel to filter |
| `PlSqlParser.create(conf).parse(String)` | throws `RecognitionException` on bad parse (recovery off) |
| `AstScanner(checks, formsMetadata, isErrorRecoveryEnabled, charset=UTF_8)` | `.scanFile(PlSqlFile): AstScannerResult` |
| `AstScannerResult` | `.issues: List<ZpaIssue>`, `.symbols`, `.linesOfCode`, `.linesOfComments`, `.numberOfStatements`, `.complexity`, `.numberOfFunctions`, `.executableLines: Set<Int>` |
| `ZpaIssue` | `.check: PlSqlCheck`, `.primaryLocation: IssueLocation` |
| `IssueLocation` | `.startLine()`, `.startLineOffset()`, `.endLine()`, `.endLineOffset()`, `.message()` |