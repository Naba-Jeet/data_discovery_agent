"""
Executor node — calls MCP tools via SSE based on intent.
"""
import re, json, traceback, httpx, os
from unittest import result
from agent.intent import extract_frequency
from mcp_client.client import (
    run_query, detect_anomalies, nl_to_sql, get_schema,
    run_dq_checks, add_dq_rule, get_dq_rules,
    detect_volume_anomalies,detect_row_anomaly
)
from agent.intent import extract_granularity, extract_threshold, extract_grain_cols
from typing import Any
from memory.store import MemoryStore
from config import MEMORY_DSN
from agent.intent import extract_frequency
from mcp_client.client import run_query, run_databricks_query
from mcp_client.client import nl_to_sql as mcp_nl_to_sql
from ml.explain.llm_explain import explain_anomalies




NO_LLM_INTENTS = {"dq", "schema", "query", "anomaly", "volume_anomaly", "row_anomaly"}

_mem = MemoryStore(MEMORY_DSN)

def _extract_granularity(message: str) -> str:
    msg = message.lower()
    if re.search(r"\b(daily|day)\b", msg):
        return "day"
    if re.search(r"\b(weekly|week)\b", msg):
        return "week"
    if re.search(r"\b(monthly|month)\b", msg):
        return "month"
    if re.search(r"\b(quarterly|quarter)\b", msg):
        return "quarter"
    if re.search(r"\b(yearly|annual|year)\b", msg):
        return "month"   # fallback — no yearly in tool yet
    return "week"  # default

def _extract_sql(text: str) -> str:
    text = re.sub(r"```(?:sql)?", "", text, flags=re.IGNORECASE)  # fix the regex too
    text = text.strip("`").strip()
    text = re.sub(r"\s+", " ", text)  # ← normalize all whitespace/newlines to single space
    return text.rstrip(";").strip()


def _parse_mcp_result(raw) -> dict:
    if isinstance(raw, list) and raw:
        text = raw[0].text if hasattr(raw[0], "text") else str(raw[0])
    else:
        text = str(raw)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"result": parsed}
    except Exception:
        result = _parse_mcp_result(raw)
        print(f"DEBUG _parse_mcp_result type={type(result)} value={result}")
        return {"result": text}


async def executor_node(state: dict[str, Any]) -> dict[str, Any]:
    

    try:

        intent        = state.get("intent", "unknown")
        user_message  = state.get("user_message", "")
        llm_response  = state.get("llm_response", "")
        pg_schema     = state.get("pg_schema", "public")
        warehouse     = state.get("warehouse", "postgres")

        result = {}

        print(f"EXECUTOR CALLED: intent={intent}, warehouse={warehouse}")

        

        if intent == "schema":
            raw = await get_schema(pg_schema)
            result = _parse_mcp_result(raw)

        elif intent == "nl_to_sql":
            # llm_response is JSON from tool_nl_to_sql → parse generated_sql
            if warehouse == "databricks":
                OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
                OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
                schema_hint = state.get("schema_context", "")
                prompt = (
                        f"Generate a valid SQL SELECT query for Databricks for: {user_message}\n"
                        f"{'Use these exact column names from the table: ' + schema_hint if schema_hint else ''}\n"
                        "The table name must be used exactly as mentioned by the user (e.g. catalog.schema.table).\n"
                        "Return ONLY raw SQL. No explanations, no markdown, no code fences."
                    )
                async with httpx.AsyncClient(timeout=180) as client:
                    resp = await client.post(f"{OLLAMA_URL}/api/generate", json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False
                    })
                    raw_sql = resp.json().get("response", "").strip()
                sql = _extract_sql(raw_sql)
                raw = await run_databricks_query(sql, token=state.get("databricks_token", ""))
                result = _parse_mcp_result(raw)
                result["generated_sql"] = sql
            else:
                # Postgres: call MCP tool directly
                raw = await nl_to_sql(pg_schema, user_message)
                parsed = _parse_mcp_result(raw)
                sql = parsed.get("generated_sql", "")
                if sql:
                    raw2 = await run_query(sql)
                    result = _parse_mcp_result(raw2)
                    result["generated_sql"] = sql
                else:
                    result = {"error": "Could not generate SQL", "detail": parsed}

        elif intent == "query":
            sql = _extract_sql(user_message)
            if not re.match(r'^\s*(select|with|show|describe|explain)\b', sql, re.IGNORECASE):
                result = {"error": f"Could not extract valid SQL from: {user_message}"}
            elif warehouse == "databricks":
                raw = await run_databricks_query(sql, token=state.get("databricks_token", ""))
            else:
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
        elif intent == "dq":
            user_msg = user_message.lower()
            table = state.get("target_table", "")
            print(f"DEBUG dq branch: user_msg={user_msg!r}, table={table!r}")
            print(f"DEBUG dq state keys: rule_type={state.get('rule_type')}, column_name={state.get('column_name')}, severity={state.get('severity')}")

            if "add" in user_msg or "create" in user_msg or "register" in user_msg:
                print("DEBUG → add_dq_rule branch")
                raw = await add_dq_rule(
                    pg_schema,
                    table,
                    state.get("rule_type", "null"),
                    state.get("column_name", ""),
                    state.get("parameters", "{}"),
                    state.get("severity", "warn"),
                )
                print(f"DEBUG add_dq_rule raw response: {raw!r}")
                result = _parse_mcp_result(raw)
            elif "rules" in user_msg or "list" in user_msg:
                print("DEBUG → get_dq_rules branch")
                raw = await get_dq_rules(pg_schema, table)
                result = _parse_mcp_result(raw)
            else:
                print("DEBUG → run_dq_checks branch")
                raw = await run_dq_checks(pg_schema, table)
                result = _parse_mcp_result(raw)

        elif intent == "volume_anomaly":
            table       = state.get("target_table", "")
            if not table:
                result = {"error": "Could not determine table for volume anomaly detection."}
            else:
                granularity   = extract_granularity(user_message)
                threshold_pct = extract_threshold(user_message)
                grain_cols    = extract_grain_cols(user_message)
                raw = await detect_volume_anomalies(
                    pg_schema,
                    table,
                    granularity=granularity,
                    threshold_pct=threshold_pct,
                    grain_cols=grain_cols,
                )
                result = _parse_mcp_result(raw)

        elif intent == "row_anomaly":

            frequency = extract_frequency(state.get("user_message", "")) or "monthly"
            table     = state.get("target_table", "")
            schema    = state.get("pg_schema", "public")

            if not table:
                result = {"error": "No table specified. Please mention a table name."}
            else:
                raw = await detect_row_anomaly(
                    schema_name=schema,
                    table_name=table,
                    frequency=frequency,
                )
                result = _parse_mcp_result(raw)
        else:
            result = {"info": "No tool execution needed for this intent."}

        if state.get("explain") and "error" not in result:
            
            table = state.get("target_table", "")
            explanation = await explain_anomalies({
                "table": table,
                "type": intent,
                "summary": result.get("decomposition_summary") or result.get("summary") or {},
                "anomalies": (
                    result.get("anomalies")
                    or result.get("result")
                    or result.get("rows")
                    or []
                )[:5],
            })
            state["explanation"] = explanation

        state["tool_result"] = result

        # Persist successful result to query_memory
        if "error" not in state.get("tool_result", {}):
            sql = state["tool_result"].get("generated_sql", "")
            tables = re.findall(r'FROM\s+([\w.]+)|JOIN\s+([\w.]+)', sql, re.IGNORECASE)
            tables_flat = [t for pair in tables for t in pair if t]
            keywords = user_message.lower().split()
            await _mem.save_query(
                intent=intent,
                question=user_message,
                tool_result=state["tool_result"],
                sql_used=sql,
                tables=tables_flat,
                keywords=keywords,
            )
            
        return state
    except Exception as e:
        print("EXECUTOR ERROR:", str(e))
        traceback.print_exc()
        state["tool_result"] = {"error": str(e)}
        return state

