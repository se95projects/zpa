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
        // Shared corpus — single source of truth for this oracle and the Python
        // parity test. Working dir at test time is the module dir (zpa-core).
        val corpusFile = File("../python/parity/corpus.json").canonicalFile
        check(corpusFile.exists()) { "parity corpus not found: $corpusFile" }

        val cases = mapper.readTree(corpusFile).get("cases")
            ?: error("corpus.json has no 'cases' object: $corpusFile")

        for ((name, sqlNode) in cases.properties()) {
            dump(name, sqlNode.asText())
        }
    }
}