"""
Formatter node — structures final response from tool_result + llm_response.
Writes to state['final_response'].
"""
import json
from typing import Any


def _table_to_markdown(columns: list, rows: list) -> str:
    if not columns or not rows:
        return "_No rows returned._"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = "\n".join(
        "| " + " | ".join(str(r.get(c, "")) for c in columns) + " |"
        for r in rows
    )
    return "\n".join([header, sep, body])


async def formatter_node(state: dict[str, Any]) -> dict[str, Any]:
    intent = state.get("intent", "unknown")
    llm_response = state.get("llm_response", "")
    tool_result = state.get("tool_result", {})

    parts = []

    # For nl_to_sql: skip raw JSON llm_response, show generated SQL instead
    if intent == "nl_to_sql":
        sql = tool_result.get("generated_sql", "")
        if sql:
            parts.append(f"🧠 **Generated SQL:**\n```sql\n{sql}\n```")
    elif llm_response:
        parts.append(llm_response)

    # Tool result rendering
    if tool_result:
        if "error" in tool_result:
            parts.append(f"\n⚠️ **Error:** {tool_result['error']}")

        elif intent in ("nl_to_sql", "query") and "rows" in tool_result:
            count = tool_result.get("row_count", 0)
            parts.append(f"\n📊 **Query Results** ({count} rows)\n")
            parts.append(_table_to_markdown(tool_result["columns"], tool_result["rows"]))

        elif intent == "schema" and isinstance(tool_result, dict):
            lines = ["\n📋 **Schema Overview**\n"]
            for table, meta in tool_result.items():
                cols = meta.get("columns", []) if isinstance(meta, dict) else []
                col_str = ", ".join(f"`{c['name']}`" for c in cols)  # was c['column']
                lines.append(f"**{table}**: {col_str}")
            parts.append("\n".join(lines))

        elif intent == "anomaly":
            parts.append(f"\n🔍 **Anomaly Detection Result:**\n```json\n{json.dumps(tool_result, indent=2)}\n```")

        else:
            parts.append(f"\n```json\n{json.dumps(tool_result, indent=2)}\n```")

    state["final_response"] = "\n".join(parts).strip()
    return state