"""
pgvector memory store — schema_memory + query_memory.
"""
import json
import asyncpg
from typing import Any
from memory.embeddings import embed
from config import MEMORY_DSN   # add this to config.py


class MemoryStore:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.dsn)
        return self._pool

    # ── Schema Memory ─────────────────────────────────────────────────────────

    async def save_schema(self, schema_name: str, table_name: str, metadata: dict):
        pool = await self._get_pool()
        text = f"{schema_name}.{table_name} " + " ".join(
            c["name"] for c in metadata.get("columns", [])
        )
        vector = embed(text)
        await pool.execute(
            """
            INSERT INTO schema_memory (schema_name, table_name, metadata, embedding, updated_at)
            VALUES ($1, $2, $3::jsonb, $4::vector, now())
            ON CONFLICT (schema_name, table_name)
            DO UPDATE SET metadata = EXCLUDED.metadata,
                          embedding = EXCLUDED.embedding,
                          updated_at = now()
            """,
            schema_name, table_name, json.dumps(metadata), str(vector)
        )

    async def get_schema(self, schema_name: str, table_name: str) -> dict | None:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            """
            SELECT metadata FROM schema_memory
            WHERE schema_name = $1 AND table_name = $2
            """,
            schema_name, table_name
        )
        return json.loads(row["metadata"]) if row else None

    async def search_schema(self, query: str, schema_name: str, limit: int = 5) -> list[dict]:
        pool = await self._get_pool()
        vector = embed(query)
        rows = await pool.fetch(
            """
            SELECT table_name, metadata,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM schema_memory
            WHERE schema_name = $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
            """,
            str(vector), schema_name, limit
        )
        return [
            {"table_name": r["table_name"], "metadata": json.loads(r["metadata"]), "similarity": r["similarity"]}
            for r in rows
        ]

    # ── Query Memory ──────────────────────────────────────────────────────────

    async def save_query(
        self,
        intent: str,
        question: str,
        tool_result: dict,
        sql_used: str = "",
        tables: list[str] = [],
        keywords: list[str] = [],
    ):
        pool = await self._get_pool()
        vector = embed(question)
        await pool.execute(
            """
            INSERT INTO query_memory
                (intent, question, tool_result, sql_used, tables, keywords, embedding)
            VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7::vector)
            """,
            intent, question, json.dumps(tool_result),
            sql_used, tables, keywords, str(vector)
        )

    async def search_query(self, question: str, intent: str = None, limit: int = 3) -> list[dict]:
        pool = await self._get_pool()
        vector = embed(question)
        if intent:
            rows = await pool.fetch(
                """
                SELECT intent, question, tool_result, sql_used, tables, keywords,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM query_memory
                WHERE intent = $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
                """,
                str(vector), intent, limit
            )
        else:
            rows = await pool.fetch(
                """
                SELECT intent, question, tool_result, sql_used, tables, keywords,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM query_memory
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                str(vector), limit
            )
        return [
            {
                "intent": r["intent"],
                "question": r["question"],
                "tool_result": json.loads(r["tool_result"]),
                "sql_used": r["sql_used"],
                "tables": r["tables"],
                "keywords": r["keywords"],
                "similarity": r["similarity"],
            }
            for r in rows
        ]