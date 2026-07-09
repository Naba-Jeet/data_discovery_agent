"""
Executor node — calls MCP tools via SSE based on intent.
"""
import re
import json
from mcp_client.client import run_query, detect_anomalies, nl_to_sql, get_schema
from typing import Any


def _extract_sql(text: str) -> str:
    text = re.sub(r"```(?:sql)?", "", text, flags=re.IGNORECASE).strip("`").strip()
    return text.rstrip(";").strip()


def _parse_mcp_result(raw) -> dict:
    """FastMCP returns list of TextContent; parse inner JSON if possible."""
    if isinstance(raw, list) and raw:
        text = raw[0].text if hasattr(raw[0], "text") else str(raw[0])
    else:
        text = str(raw)
    try:
        return json.loads(text)
    except Exception:
        return {"result": text}


async def executor_node(state: dict[str, Any]) -> dict[str, Any]:
    intent        = state.get("intent", "unknown")
    user_message  = state.get("user_message", "")
    llm_response  = state.get("llm_response", "")
    pg_schema     = state.get("pg_schema", "public")

    result = {}

    if intent == "schema":
        raw = await get_schema(pg_schema)
        result = _parse_mcp_result(raw)

    elif intent == "nl_to_sql":
        # llm_response is JSON from tool_nl_to_sql → parse generated_sql
        print("DEBUG llm_response:", llm_response)
        sql = ""
        try:
            parsed = json.loads(llm_response)
            sql = parsed.get("generated_sql", "")
            if parsed.get("error"):
                state["tool_result"] = {
                    "error": parsed["error"],
                    "generated_sql": parsed.get("generated_sql", ""),
                    "sql": ""
                }
                return state
        except Exception:
            sql = llm_response  # fallback: treat as raw SQL

        sql = _extract_sql(sql)
        raw = await run_query(sql)
        result = _parse_mcp_result(raw)
        # Normalize if MCP returned a raw list of rows
        if isinstance(result, list):
            cols = list(result[0].keys()) if result else []
            result = {
                "rows": result,
                "columns": cols,
                "row_count": len(result)
            }

        result["generated_sql"] = sql
        print("DEBUG tool_result keys:", result.keys())  # add this
        print("DEBUG tool_result:", result)               # add this
        result["generated_sql"] = sql  # carry forward for formatter

    elif intent == "query":
        sql = _extract_sql(user_message)
        raw = await run_query(sql)
        result = _parse_mcp_result(raw)

    elif intent == "anomaly":
        table  = state.get("target_table", "")
        column = state.get("target_column", "")
        if table:
            raw = await detect_anomalies(pg_schema, table)
            result = _parse_mcp_result(raw)
        else:
            result = {"error": "Could not determine table for anomaly detection."}

    else:
        result = {"info": "No tool execution needed for this intent."}

    state["tool_result"] = result
    return state