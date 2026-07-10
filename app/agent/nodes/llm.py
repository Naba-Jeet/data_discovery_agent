"""
LLM node — calls Ollama for intents that need narrative/explanation.
For nl_to_sql, delegates to MCP tool_nl_to_sql instead (LLM already inside MCP).
"""
import json
import httpx
from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from agent.prompt_router import get_system_prompt
from mcp_client.client import nl_to_sql
from typing import Any

TIMEOUT = httpx.Timeout(120.0)


def _parse_mcp_result(raw) -> str:
    if isinstance(raw, list) and raw:
        return raw[0].text if hasattr(raw[0], "text") else str(raw[0])
    return str(raw)


async def llm_node(state: dict[str, Any]) -> dict[str, Any]:
    intent       = state.get("intent", "unknown")
    user_message = state.get("user_message", "")
    schema_ctx   = state.get("schema_context", "")

    # nl_to_sql → use MCP tool (it already calls Ollama internally)
    if intent in ("nl_to_sql", "schema", "anomaly", "dq"):
        if intent == "nl_to_sql":
            schema_ctx = state.get("schema_context", "")
            table_hints = []
            for line in schema_ctx.splitlines():
                if line.startswith("Table:"):
                    table_hints.append(line.replace("Table:", "").strip())

            enriched_question = user_message
            if table_hints:
                enriched_question += f"\n\nAvailable tables: {', '.join(table_hints)}"

            similar_sql = state.get("similar_sql", "")
            if similar_sql:
                enriched_question += f"\n\n{similar_sql}"

            raw = await nl_to_sql(
                schema_name=state.get("pg_schema", "public"),
                question=enriched_question,
            )
            state["llm_response"] = _parse_mcp_result(raw)
            return state

    # All other intents → call Ollama directly
    system_prompt = get_system_prompt(intent)
    user_content  = user_message
    if schema_ctx:
        user_content = f"Schema Context:\n{schema_ctx}\n\nQuestion: {user_message}"

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            resp.raise_for_status()
            state["llm_response"] = resp.json()["message"]["content"].strip()
    except Exception as e:
        state["llm_response"] = f"[LLM error: {e}]"

    return state
