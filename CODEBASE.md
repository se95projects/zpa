# ZPA Codebase Reference

**ZPA (Z PL/SQL Analyzer)** is a parser and static code analysis tool for PL/SQL and Oracle SQL. Its primary delivery is a SonarQube plugin, but the core is a standalone library that can be embedded or called independently.

---

## 1. Module Structure

The Gradle multi-project build (`settings.gradle.kts`) defines five subprojects:

| Module | Purpose |
|---|---|
| `zpa-core` | Lexer, parser, grammar, AST walker, symbol table, metrics |
| `zpa-checks` | 53 built-in coding rules |
| `zpa-checks-testkit` | `PlSqlCheckVerifier` — test harness for writing rule tests |
| `zpa-toolkit` | Swing GUI to visualize the AST interactively |
| `sonar-zpa-plugin` | SonarQube integration (sensors, metrics import, utPLSQL) |

Additionally `plsql-custom-rules` is a standalone demo (has its own Gradle wrapper) showing how to ship custom rules as a plugin.

**Build toolchain**

- Kotlin 2.3.x (JVM target Java 21) — all source is Kotlin
- FLR 1.5.0 (`com.felipebz.flr`) — the lexer/parser framework (a fork of SonarSource's SSLR)
- Jackson 2.21.x — JSON/XML serialization
- JUnit 6.x + AssertJ for tests

The devcontainer image is `python:3.14.2` (no JDK installed by default). Running Gradle requires a JDK 21 to be available.

---

## 2. Core Architecture

### 2.1 Pipeline

```
SQL source text
    │
    ▼
PlSqlLexer          → token stream
    │
    ▼
PlSqlParser         → AST (tree of SemanticAstNode)
    │
    ▼
PlSqlAstWalker      → dispatches visitNode/leaveNode to registered visitors
    ├── SymbolVisitor       (scope + symbol resolution)
    ├── MetricsVisitor      (LOC, statements, complexity)
    ├── ComplexityVisitor
    └── PlSqlCheck subclasses  (each produces zero or more issues)
    │
    ▼
AstScannerResult    (issues, symbols, metrics)
```

### 2.2 FLR — the parsing framework

ZPA uses **FLR** (`com.felipebz.flr`), the author's Kotlin fork of SonarSource's SSLR. Key concepts:

- `Lexer` — transforms raw text into a flat `Token` list via a chain of **Channels**.
- `Parser<Grammar>` — uses a `LexerfulGrammarBuilder`-produced grammar to build an AST from the token stream.
- `AstNode` — every node in the tree. Extended here as `SemanticAstNode`.
- `GrammarRuleKey` — an enum constant that names a grammar rule (e.g. `PlSqlGrammar.SELECT_STATEMENT`).

---

## 3. Lexer (`zpa-core`)

**File:** `zpa-core/src/main/kotlin/com/felipebz/zpa/lexer/PlSqlLexer.kt`

`PlSqlLexer.create(conf)` returns a configured FLR `Lexer`. Channels are applied in order; the first one that consumes at least one character wins:

| Channel | What it consumes |
|---|---|
| `DiscardWhitespaceChannel` | All whitespace (not stored) |
| `CommentChannel` | `--` line comments and `/* */` block comments (stored as trivia) |
| `NumericChannel` | Floating-point numbers (regex-based) |
| `IntegerChannel` | Plain integers |
| `StringChannel` | `'...'`, `n'...'`, `q'[...]'`, etc. |
| `DateChannel` | `DATE 'YYYY-MM-DD'` and `TIMESTAMP '...'` literals |
| `IdentifierChannel` | Simple identifiers and **keywords** (via `IdentifierAndKeywordChannel`) |
| `QuotedIdentifierChannel` | `"quoted identifiers"` |
| `PunctuatorChannel` | All `PlSqlPunctuator` values |
| `BlackHoleChannel` | Conditional compilation directives (`$IF … $THEN`, etc.) |
| `UnknownCharacterChannel` | Catch-all for unexpected characters |

Token types are defined in `PlSqlTokenType` (5 literal types), `PlSqlKeyword` (reserved + non-reserved keywords), and `PlSqlPunctuator`.

**Key detail:** The lexer is case-insensitive for keywords (regex flag `(?i)`). Identifiers are matched with a Unicode-aware pattern (`[\w\p{L}][\w\p{L}#$]*`).

---

## 4. Grammar (`zpa-core`)

**Entry point:** `PlSqlGrammar.create(conf): PlSqlGrammarBuilder`

The grammar is an **enum** — `PlSqlGrammar` — where each enum constant is a `GrammarRuleKey`. Rules are defined in static companion methods:

| Method | Grammar rules created |
|---|---|
| `createLiterals` | `LITERAL`, `BOOLEAN_LITERAL`, `INTERVAL_LITERAL`, etc. |
| `createOperators` | Comparison / concatenation operators |
| `createDatatypes` | `DATATYPE`, `NUMERIC_DATATYPE`, `CHARACTER_DATAYPE`, etc. |
| `createStatements` | All PL/SQL statements (`IF_STATEMENT`, `FOR_STATEMENT`, `SELECT_STATEMENT`, …) |
| `createExpressions` | Expression precedence tower |
| `createDeclarations` | Variables, cursors, records, pragmas, procedures, functions |
| `createTrigger` | `CREATE_TRIGGER` and all trigger variants |
| `createProgramUnits` | `CREATE_PROCEDURE`, `CREATE_FUNCTION`, `CREATE_PACKAGE`, `CREATE_VIEW`, etc. |
| `DdlGrammar.buildOn` | DDL: `CREATE TABLE`, `ALTER TABLE`, `DROP`, etc. |
| `DmlGrammar.buildOn` | DML: `SELECT_EXPRESSION`, `INSERT_EXPRESSION`, `UPDATE_EXPRESSION`, `MERGE_EXPRESSION` |
| `DclGrammar.buildOn` | `GRANT`, `REVOKE` |
| `TclGrammar.buildOn` | `COMMIT`, `ROLLBACK`, `SAVEPOINT`, `SET TRANSACTION` |
| `SqlPlusGrammar.buildOn` | SQL*Plus commands (`/`, `@`, `@@`, `PROMPT`, etc.) |
| `SessionControlGrammar.buildOn` | `ALTER SESSION`, `ALTER SYSTEM` |
| `SingleRowSqlFunctionsGrammar.buildOn` | Built-in single-row SQL functions |
| `AggregateSqlFunctionsGrammar.buildOn` | Aggregate / analytic SQL functions |
| `ConditionsGrammar.buildOn` | `IS NULL`, `LIKE`, `BETWEEN`, `REGEXP_LIKE`, JSON conditions, etc. |

**Root rule:** `FILE_INPUT` — zero-or-more `VALID_INPUT` entries followed by `EOF`. When error recovery is enabled, a `RECOVERY` rule absorbs unrecognized tokens between valid entries, so a file with one bad statement doesn't fail the whole parse.

**Expression precedence** (lowest to highest, left-to-right within each level):

```
EXPRESSION = BOOLEAN_EXPRESSION
  OR_EXPRESSION      (OR)
  AND_EXPRESSION     (AND)
  NOT_EXPRESSION     (NOT prefix)
  COMPARISON_EXPRESSION  (conditions + IN)
  IN_EXPRESSION      (NOT? IN (...))
  CONCATENATION_EXPRESSION  (||)
  ADDITIVE_EXPRESSION       (+ -)
  MULTIPLICATIVE_EXPRESSION (* / MOD)
  EXPONENTIATION_EXPRESSION (**)
  UNARY_EXPRESSION    (+ - PRIOR CONNECT_BY_ROOT EXISTS MULTISET NEW CASE)
  POSTFIX_EXPRESSION  (obj_ref + analytic/keep clause)
  OBJECT_REFERENCE   (call chains, member access)
  METHOD_CALL / QUALIFIED_EXPRESSION
  MEMBER_EXPRESSION  (dotted names, collection attributes)
  MULTIPLE_VALUE_EXPRESSION
  BRACKED_EXPRESSION / PRIMARY_EXPRESSION
```

---

## 5. AST Nodes

**`SemanticAstNode`** (`zpa-core/src/main/kotlin/…/api/squid/SemanticAstNode.kt`) extends FLR's `AstNode` with:

| Field | Type | Purpose |
|---|---|---|
| `symbol` | `Symbol?` | The resolved symbol for an identifier reference |
| `plSqlDatatype` | `PlSqlDatatype` | Resolved data type (falls back to symbol's type) |
| `plSqlType` | `PlSqlType` | Enum summary: `NUMERIC`, `CHARACTER`, `DATE`, `BOOLEAN`, `ROWTYPE`, `ASSOCIATIVE_ARRAY`, `UNKNOWN`, … |
| `tree` | `Tree` | Typed facade (e.g. `IfStatement`) for structured traversal |
| `allTokensToString` | `String` | Concatenated source tokens for the subtree |

The **`Tree`** interface (`sslr/Tree.kt`) is a typed wrapper over `SemanticAstNode`. Grammar rules can be bound to a specific `Tree` subclass via `b.rule(IF_STATEMENT, IfStatement::class)` in `PlSqlGrammarBuilder`, enabling type-safe access to tree structure.

---

## 6. Visitor Pattern

### PlSqlVisitor (base)

**File:** `zpa-core/src/main/kotlin/…/api/checks/PlSqlVisitor.kt`

```kotlin
open class PlSqlVisitor {
    fun subscribeTo(vararg astNodeTypes: AstNodeType)  // register interest
    open fun init()           // called once per file, set up subscriptions here
    open fun startScan()      // called before each file
    open fun visitFile(node: AstNode)
    open fun visitNode(node: AstNode)  // called when entering a subscribed node
    open fun visitToken(token: Token)
    open fun visitComment(trivia: Trivia, content: String)
    open fun leaveNode(node: AstNode)  // called when leaving a subscribed node
    open fun leaveFile(node: AstNode)
}
```

### PlSqlCheck (check base class)

**File:** `zpa-core/src/main/kotlin/…/api/checks/PlSqlCheck.kt`

Extends `PlSqlVisitor` and adds issue-reporting methods:

```kotlin
fun addIssue(node: AstNode, message: String): PreciseIssue
fun addIssue(tree: Tree, message: String): PreciseIssue
fun addLineIssue(message: String, lineNumber: Int): PreciseIssue
fun addFileIssue(message: String): PreciseIssue
```

`PreciseIssue` carries a primary `IssueLocation` (line + column range + message) and optional secondary locations.

### PlSqlAstWalker

**File:** `zpa-core/src/main/kotlin/…/squid/PlSqlAstWalker.kt`

1. Calls `init()` on all visitors → they call `subscribeTo(...)`.
2. Builds a map `AstNodeType → List<PlSqlVisitor>`.
3. Recursively walks the AST: for each node, dispatches `visitNode` to subscribed visitors, then recurses into children, then dispatches `leaveNode`.
4. Tokens and their trivia (comments) are dispatched to all visitors.

### Writing a check — pattern

```kotlin
@Rule(priority = Priority.MAJOR, tags = [Tags.BUG])
@ConstantRemediation("5min")
@RuleInfo(scope = RuleInfo.Scope.ALL)
@ActivatedByDefault
class MyCheck : AbstractBaseCheck() {
    override fun init() {
        subscribeTo(PlSqlGrammar.SELECT_STATEMENT)
    }
    override fun visitNode(node: AstNode) {
        // inspect node, call addIssue(...) if needed
    }
}
```

`AbstractBaseCheck` adds `getLocalizedMessage()` which looks up the rule message from `org/sonar/l10n/plsqlopen.properties` by key `<CheckClassName>.message`.

---

## 7. Symbol Table and Semantic Analysis

### SymbolVisitor

**File:** `zpa-core/src/main/kotlin/…/symbols/SymbolVisitor.kt`

Runs as the **first visitor** on every file. Visits `CREATE_PROCEDURE`, `CREATE_FUNCTION`, `CREATE_PACKAGE`, `BLOCK_STATEMENT`, `FOR_STATEMENT`, `CURSOR_DECLARATION`, `SELECT_EXPRESSION`, etc. to build a scope tree.

Key scope holders: procedures/functions, packages, anonymous blocks, for-loops, cursor declarations, select expressions.

For each variable/parameter declaration it creates a `Symbol` and attaches it to the `SemanticAstNode` for every usage it finds.

### Symbol and Scope

| Interface | File | Description |
|---|---|---|
| `Symbol` | `api/symbols/Symbol.kt` | Name, type, declaration node, list of usage nodes |
| `Scope` | `api/symbols/Scope.kt` | Parent scope, list of symbols |
| `SymbolTable` | `api/symbols/SymbolTable.kt` | Maps nodes → symbols and symbols → scopes |
| `ScopeImpl` | `symbols/ScopeImpl.kt` | Concrete scope implementation |
| `SymbolTableImpl` | `symbols/SymbolTableImpl.kt` | Concrete symbol table |
| `DefaultTypeSolver` | `symbols/DefaultTypeSolver.kt` | Resolves data type from declaration |

### PlSqlDatatype hierarchy

```
PlSqlDatatype (sealed interface)
├── NumericDatatype
├── CharacterDatatype
├── BooleanDatatype
├── DateDatatype
├── LobDatatype
├── JsonDatatype
├── RecordDatatype
├── RowtypeDatatype
├── AssociativeArrayDatatype
├── ExceptionDatatype
├── NullDatatype
└── UnknownDatatype   (default when type cannot be resolved)
```

---

## 8. Scanner Entry Points

### AstScanner (production)

**File:** `zpa-core/src/main/kotlin/…/squid/AstScanner.kt`

```kotlin
val scanner = AstScanner(
    checks = listOf(MyCheck(), ...),
    formsMetadata = null,
    isErrorRecoveryEnabled = true
)
val result: AstScannerResult = scanner.scanFile(plSqlFile)
// result.issues, result.symbols, result.linesOfCode, etc.
```

`PlSqlFile` is a one-method interface:
```kotlin
interface PlSqlFile {
    fun contents(): String
    fun fileName(): String
    fun path(): Path
    fun type(): Type    // MAIN or TEST
}
```

### TestPlSqlVisitorRunner (test/standalone)

**File:** `zpa-core/src/main/kotlin/…/TestPlSqlVisitorRunner.kt`

Lower-level runner used by tests and `PlSqlCheckVerifier`:
```kotlin
TestPlSqlVisitorRunner.scanFile(file, metadata, symbolVisitor, myCheck)
```
Parses the file with UTF-8 / no error recovery, creates a `PlSqlVisitorContext`, and runs all supplied visitors through `PlSqlAstWalker`.

### PlSqlConfiguration

```kotlin
PlSqlConfiguration(charset: Charset, isErrorRecoveryEnabled: Boolean = false)
```

---

## 9. Built-in Checks (zpa-checks)

53 checks registered in `CheckList.checks`. A representative sample:

| Check | Rule | What it detects |
|---|---|---|
| `SelectAllColumnsCheck` | MAJOR | `SELECT *` |
| `ComparisonWithNullCheck` | BLOCKER | `col = NULL` instead of `IS NULL` |
| `InsertWithoutColumnsCheck` | MAJOR | `INSERT INTO t VALUES (...)` without column list |
| `EmptyBlockCheck` | MAJOR | `BEGIN ... END` with no statements |
| `UnusedVariableCheck` | MAJOR | Declared but never used variables |
| `VariableHidingCheck` | MAJOR | Inner variable shadows outer variable |
| `ToDateWithoutFormatCheck` | MAJOR | `TO_DATE(str)` without format mask |
| `CommitRollbackCheck` | MAJOR | `COMMIT`/`ROLLBACK` inside stored procedure |
| `QueryWithoutExceptionHandlingCheck` | MAJOR | DML inside a block without `NO_DATA_FOUND` handler |
| `ComparisonWithBooleanCheck` | MAJOR | `IF flag = TRUE` (redundant comparison) |
| `DeadCodeCheck` | MAJOR | Code after unconditional `RETURN`/`RAISE` |
| `ParsingErrorCheck` | MAJOR | File that could not be parsed at all |
| `XPathCheck` | varies | Configurable XPath-based rule |

Checks carry annotations:
- `@Rule(priority, tags)` — severity and category tags
- `@ActivatedByDefault` — included in "Sonar way" profile
- `@RuleInfo(scope)` — `MAIN`, `TEST`, or `ALL`
- `@ConstantRemediation("Xmin")` — SonarQube remediation effort

---

## 10. Test Infrastructure (zpa-checks-testkit)

`PlSqlCheckVerifier` (`zpa-checks-testkit`) allows testing checks with annotated SQL files:

```sql
select * -- Noncompliant {{SELECT * should not be used.}}
  into var from emp;

select *  -- Noncompliant [[sc=8;ec=9]]
  into row from emp;
```

Comment markers:
- `-- Noncompliant` — expect an issue on this line
- `{{message}}` — expect exactly this message text
- `[[sc=N;ec=M]]` — expect issue at columns N–M
- `[[secondary=+1,+3]]` — expect secondary locations at offsets
- `@+N` / `@-N` — shift expected issue line

Usage in a test:
```kotlin
@Test
fun test() {
    PlSqlCheckVerifier.verify("src/test/resources/checks/select_all_columns.sql", SelectAllColumnsCheck())
}
```

Grammar-level parser tests extend `RuleTest`:
```kotlin
class SelectExpressionTest : RuleTest() {
    @BeforeEach fun init() { setRootRule(DmlGrammar.SELECT_EXPRESSION) }

    @Test fun matchesSimpleSelect() {
        assertThat(p).matches("select 1 from dual")
    }
}
```

`assertThat(p).matches(...)` comes from `flr-testing-harness`.

---

## 11. SonarQube Plugin (sonar-zpa-plugin)

**Entry point:** `PlSqlPlugin` registers all SonarQube extensions.

Key components:

| Component | Role |
|---|---|
| `PlSql` | Language definition (key `plsqlopen`, file extensions `.sql`, `.pkg`, etc.) |
| `PlSqlProfile` | "Sonar way" quality profile — all `@ActivatedByDefault` checks |
| `PlSqlRuleRepository` | Registers all checks from `CheckList` into SonarQube |
| `PlSqlSquidSensor` | Main sensor — scans files, runs `AstScanner`, publishes issues and metrics |
| `PlSqlHighlighterVisitor` | Syntax highlighting |
| `CpdVisitor` | Copy-paste detection token emission |
| `SonarQubeSymbolTable` | Publishes symbol usage data to SonarQube |
| `UtPlSqlSensor` | Imports utPLSQL test results and coverage XML |

The SonarQube adapters (`SonarQubeActiveRuleAdapter`, etc.) translate between ZPA's internal rule model and SonarQube's plugin API.

---

## 12. ZPA Toolkit

A standalone Swing application (`zpa-toolkit/src/main/kotlin/…/toolkit/ZpaToolkit.kt`) that lets you paste PL/SQL code and see the resulting AST in a tree view alongside the symbol table. Useful for developing or debugging rules and grammar.

Launch:
```
./gradlew :zpa-toolkit:run
```

---

## 13. Building the Project

### Prerequisites
- JDK 21 (required by `kotlin-conventions.gradle.kts`)
- Gradle Wrapper (`./gradlew`) handles all other dependencies

### Common tasks

```bash
# Full build + unit tests
./gradlew build

# Build without tests
./gradlew build -x test

# Build and publish to local Maven cache (needed for integration tests and plsql-custom-rules)
./gradlew publishToMavenLocal

# Run unit tests only
./gradlew test

# Run all integration tests (requires SonarQube orchestrator + sqlcl download)
git submodule update --init --recursive
./gradlew integrationTest

# Run the AST Toolkit GUI
./gradlew :zpa-toolkit:run
```

### Build outputs

| Artifact | Location |
|---|---|
| `sonar-zpa-plugin-*.jar` | `sonar-zpa-plugin/build/libs/` |
| `zpa-toolkit-*-all.jar` | `zpa-toolkit/build/libs/` (fat jar via Shadow) |
| Individual module JARs | `<module>/build/libs/` |

---

## 14. Testing Against Sample SQL Queries

### Option A: Using existing unit tests

Each grammar rule has corresponding tests under `zpa-core/src/test/kotlin/…/api/`. For example:

```bash
# Run just the DML query tests
./gradlew :zpa-core:test --tests "com.felipebz.zpa.api.sql.*"

# Run all unit tests for zpa-core
./gradlew :zpa-core:test
```

### Option B: Adding a new SQL test for a grammar rule

1. Add a test class extending `RuleTest` (in `zpa-core/src/test`):

```kotlin
class MyQueryTest : RuleTest() {
    @BeforeEach fun init() { setRootRule(DmlGrammar.SELECT_EXPRESSION) }

    @Test fun parsesComplexQuery() {
        assertThat(p).matches("""
            SELECT e.emp_id, d.dept_name
              FROM employees e
              JOIN departments d ON e.dept_id = d.dept_id
             WHERE e.salary > 50000
             ORDER BY e.emp_id
        """.trimIndent())
    }
}
```

### Option C: Testing a check against a SQL file

1. Create a `.sql` file in `zpa-checks/src/test/resources/checks/`.
2. Annotate expected issues with `-- Noncompliant` comments.
3. Add a test class:

```kotlin
class MyCheckTest {
    @Test fun test() {
        PlSqlCheckVerifier.verify(
            "src/test/resources/checks/my_check.sql",
            MyCheck()
        )
    }
}
```

### Option D: Standalone programmatic invocation

The minimal code to parse and analyze a SQL string without SonarQube or file I/O:

```kotlin
import com.felipebz.zpa.api.PlSqlFile
import com.felipebz.zpa.squid.AstScanner
import com.felipebz.zpa.checks.*
import java.nio.file.Path

val sql = "select * from emp;"

val file = object : PlSqlFile {
    override fun contents() = sql
    override fun fileName() = "test.sql"
    override fun path() = Path.of("test.sql")
    override fun type() = PlSqlFile.Type.MAIN
}

val scanner = AstScanner(
    checks = listOf(SelectAllColumnsCheck(), ComparisonWithNullCheck()),
    formsMetadata = null,
    isErrorRecoveryEnabled = true
)
val result = scanner.scanFile(file)
result.issues.forEach { issue ->
    println("${issue.primaryLocation.startLine()}: ${issue.primaryLocation.message()}")
}
```

---

## 15. Python Refactoring Considerations

The core parsing logic is deeply tied to FLR (JVM library) and Kotlin. A Python port would need to reimplement:

### What needs to be reimplemented

| Component | Complexity | Notes |
|---|---|---|
| Lexer | Medium | ~8 regex-based channels; Python `re` can handle all patterns |
| Grammar rules | High | ~500+ grammar rules across 10 files; need a PEG/Earley parser framework |
| AST walker | Low | Simple recursive visitor dispatch |
| Symbol table | Medium | Scope stack + symbol resolution |
| Checks | Low-Medium | Each check is 20–80 lines; straightforward once AST is available |
| Test harness | Low | `-- Noncompliant` annotation parsing is simple |

### Recommended Python approach

**Parser framework options:**

- **`lark`** — PEG/LALR grammar, good for large grammars, produces parse trees
- **`parsimonious`** — PEG parser, readable grammar syntax
- **`antlr4`** (Python runtime) — battle-tested for SQL; Oracle SQL grammar already exists publicly

**Suggested phases:**

1. **Lexer first** — translate each `*Channel.kt` to a Python tokenizer. The regex patterns in `PlSqlLexer.kt` are directly usable with `re` (convert `(?is)` flags appropriately).
2. **Grammar skeleton** — translate the ~10 grammar files to Lark/ANTLR grammar notation. Start with `DmlGrammar` (the most self-contained and practically useful).
3. **AST walker** — implement a generic recursive descent visitor that calls `visit_<node_type>` methods.
4. **Symbol visitor** — port `SymbolVisitor.kt` to Python, tracking scope via a stack.
5. **Checks** — port `AbstractBaseCheck` and individual check classes.
6. **Test harness** — port `PlSqlCheckVerifier` to read the existing `.sql` test files (annotations are language-independent).

### Key regex patterns to carry over

```python
# From PlSqlLexer.kt — directly usable in Python with re.IGNORECASE | re.DOTALL
NUMBER_LITERAL = r"(?:(?:\d+(?!\.\.)\.?\d*)|(?!\.\.)\.?\d+)(?:e[+-]?\d+)?[fd]?"
STRING_LITERAL = r"n?'(?:[^']|'')*'"
DATE_LITERAL = r"DATE\s*'\d{4}-\d{2}-\d{2}'"
TIMESTAMP_LITERAL = r"TIMESTAMP\s*'\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}:\d{2}[^']*'"
SIMPLE_IDENTIFIER = r"[\wÀ-ɏ][\wÀ-ɏ#$]*"
QUOTED_IDENTIFIER = r'".+?"'
LINE_COMMENT = r"--[^\r\n]*"
BLOCK_COMMENT = r"/\*.*?\*/"
```

### What can be skipped initially

- SonarQube integration — skip entirely for a standalone CLI tool
- Oracle Forms metadata — skip unless needed
- XML/JSON coverage importers (utPLSQL) — skip
- ZPA Toolkit GUI — skip

---

## 16. Key File Map

| Task | Primary files |
|---|---|
| Understand the lexer | `zpa-core/…/lexer/PlSqlLexer.kt`, `*Channel.kt` files |
| Understand grammar rules | `zpa-core/…/api/PlSqlGrammar.kt`, `DmlGrammar.kt`, `DdlGrammar.kt` |
| Understand how checks work | `zpa-core/…/api/checks/PlSqlCheck.kt`, `PlSqlVisitor.kt` |
| Understand the AST walker | `zpa-core/…/squid/PlSqlAstWalker.kt` |
| Understand scanning pipeline | `zpa-core/…/squid/AstScanner.kt` |
| Find all built-in checks | `zpa-checks/…/checks/CheckList.kt` |
| See a simple check | `zpa-checks/…/checks/ComparisonWithNullCheck.kt` |
| See a complex check | `zpa-checks/…/checks/SelectAllColumnsCheck.kt` |
| Run a check in tests | `zpa-checks-testkit/…/verifier/PlSqlCheckVerifier.kt` |
| Write a grammar test | `zpa-core/src/test/…/api/RuleTest.kt` |
| Symbol resolution | `zpa-core/…/symbols/SymbolVisitor.kt`, `DefaultTypeSolver.kt` |
| Data types | `zpa-core/…/api/symbols/datatype/*.kt` |
| Token types | `zpa-core/…/api/PlSqlTokenType.kt`, `PlSqlKeyword.kt`, `PlSqlPunctuator.kt` |
