"""
RAG node — fetch schema context.
1. Check pgvector schema_memory first (cache hit)
2. On miss → call MCP get_schema_metadata → save to memory
3. For nl_to_sql → also search query_memory for similar past SQL
"""
import json
from typing import Any
from mcp_client.client import get_schema
from memory.store import MemoryStore
from config import MEMORY_DSN

_mem = MemoryStore(MEMORY_DSN)


def _unwrap_mcp(raw) -> str:
    if isinstance(raw, list) and raw:
        return raw[0].text if hasattr(raw[0], "text") else str(raw[0])
    return str(raw)


async def rag_node(state: dict[str, Any]) -> dict[str, Any]:
    intent      = state.get("intent", "unknown")
    pg_schema   = state.get("pg_schema", "public")
    user_msg    = state.get("user_message", "")
    tgt_table   = state.get("target_table", "")
    warehouse = state.get("warehouse", "postgres")

    schema_context = ""
    similar_sql    = ""

    if warehouse == "databricks" and tgt_table:
        parts = tgt_table.split(".")
        db_schema = parts[-2] if len(parts) >= 2 else "databricks"
        db_table = parts[-1]

        cached = await _mem.get_schema(db_schema, db_table)
        if cached:
            cols = cached.get("columns", [])
        else:
            from mcp_client.client import run_databricks_query
            token = state.get("databricks_token", "")
            catalog = parts[0] if len(parts) == 3 else "hive_metastore"
            schema_n = parts[1] if len(parts) == 3 else parts[0]
            table_n = parts[-1]

            raw = await run_databricks_query(
                f"DESC TABLE {tgt_table}",
                token=token
            )
            raw_str = _unwrap_mcp(raw)          # ← reuse existing function
            try:
                parsed = json.loads(raw_str)
                rows = parsed.get("rows", parsed) if isinstance(parsed, dict) else parsed
                cols = [
                    {"name": r["col_name"], "type": r["data_type"]}
                    for r in rows
                    if isinstance(r, dict) and r.get("col_name") and not r["col_name"].startswith("#")
                ]
            except Exception:
                cols = []

            if cols:
                await _mem.save_schema(db_schema, db_table, {"columns": cols})

        col_str = ", ".join(f"{c['name']} ({c['type']})" for c in cols)
        state["schema_context"] = f"Table: {tgt_table}\nColumns: {col_str}"
        state["similar_sql"] = ""
        return state

    if intent in ("nl_to_sql", "schema", "query", "anomaly", "dq"):

        # 1. Try pgvector schema cache
        if tgt_table:
            cached = await _mem.get_schema(pg_schema, tgt_table)
        else:
            cached = None

        if cached:
            # Cache hit — build context from stored metadata
            tables_meta = {tgt_table: cached} if tgt_table else {}
        else:
            # Cache miss — call MCP
            raw = await get_schema(schema_name=pg_schema)
            raw_str = _unwrap_mcp(raw)
            try:
                tables_meta = json.loads(raw_str)
            except Exception:
                tables_meta = {}

            # Save each table to schema_memory
            for tname, tmeta in tables_meta.items():
                await _mem.save_schema(pg_schema, tname, tmeta)

        # Build schema context string
        lines = []
        for tname, tmeta in tables_meta.items():
            if isinstance(tmeta, dict):
                cols = tmeta.get("columns", [])
                col_defs = ", ".join(f"{c['name']} ({c['type']})" for c in cols)
                lines.append(f"Table: {pg_schema}.{tname}\nColumns: {col_defs}")
        schema_context = "\n\n".join(lines)

        # 2. For nl_to_sql — search query_memory for similar past SQL
        if intent == "nl_to_sql":
            past = await _mem.search_query(user_msg, intent="nl_to_sql", limit=2)
            if past and past[0]["similarity"] > 0.80:
                similar_sql = "\n".join(
                    f"-- Similar past query (score {p['similarity']:.2f}):\n{p['sql_used']}"
                    for p in past if p["sql_used"]
                )

    state["schema_context"] = schema_context
    state["similar_sql"]    = similar_sql
    return state