"""
RAG node — fetches schema context via MCP SSE and injects into state.
"""
import json
from mcp_client.client import get_schema
from typing import Any


async def rag_node(state: dict[str, Any]) -> dict[str, Any]:
    intent = state.get("intent", "unknown")

    if intent not in ("schema", "nl_to_sql", "query"):
        state["schema_context"] = ""
        return state

    schema_name = state.get("pg_schema", "public")
    raw = await get_schema(schema_name)  # returns plain string (JSON) after _unwrap

    # Parse JSON string → dict
    try:
        schema_data = json.loads(raw)
    except Exception:
        state["schema_context"] = raw  # fallback: pass raw string
        return state

    # Build compact text: "table (col1 type, col2 type, ...)"
    lines = []
    for table, meta in schema_data.items():
        cols = meta.get("columns", [])
        col_defs = ", ".join(f"{c['name']} {c['type']}" for c in cols)
        lines.append(f"{table} ({col_defs})")

    state["schema_context"] = "\n".join(lines)
    return state