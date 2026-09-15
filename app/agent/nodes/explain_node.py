# app/agent/nodes/explain_node.py

import re
import json
import pandas as pd
from mcp_client.client import run_query
from ml.anomaly import detect_timeseries_anomalies, detect_outliers, detect_zscore_outliers
from ml.explain.llm_explain import explain_anomalies


def _extract_table(question: str) -> str | None:
    """
    Dynamically extract schema.table or bare table name from NL question.
    Looks for patterns like:
      - 'in sales.salesorderheader'
      - 'for public.orders'
      - 'from orders'
      - 'table customers'
    """
    # Priority 1: schema.table pattern (most specific)
    match = re.search(r'\b([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\b', question.lower())
    if match:
        return match.group(1)

    # Priority 2: keyword-anchored bare table name
    match = re.search(
        r'(?:in|for|from|on|table|of)\s+([a-z_][a-z0-9_]+)',
        question.lower()
    )
    if match:
        return match.group(1)

    return None


async def explain_node(state: dict) -> dict:
    question  = state.get("question", "")
    table     = _extract_table(question)

    if not table:
        return {**state, "output": "Please specify a table name, e.g. 'explain anomalies in sales.salesorderheader'"}

    try:
        # 1. Fetch data
        raw    = await run_query(f"SELECT * FROM {table} LIMIT 50000", limit=50000)
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        rows   = parsed if isinstance(parsed, list) else parsed.get("rows", [])
        df     = pd.DataFrame(rows)

        if df.empty:
            return {**state, "output": f"No data found in `{table}`"}

        # 2. Auto-detect date + numeric cols
        df_converted = df.copy()
        for col in df.columns:
            df_converted[col] = pd.to_numeric(df_converted[col], errors="ignore")

        date_col   = next((c for c in df.columns if "date" in c.lower()), None)
        value_cols = df_converted.select_dtypes(include="number").columns.tolist()

        results = {}

        # 3. Timeseries anomaly (if date col found)
        if date_col and value_cols:
            value_col = value_cols[0]
            df_ts = df_converted[[date_col, value_col]].copy()
            df_ts[value_col] = pd.to_numeric(df_ts[value_col], errors="coerce")
            ts_result = detect_timeseries_anomalies(
                df_ts, date_col=date_col, value_col=value_col,
                period=12, threshold=2.5, freq="ME"
            )
            results["timeseries"] = ts_result

        # 4. Column-level anomaly
        col_result = detect_zscore_outliers(df_converted, numeric_cols=value_cols[:5])
        results["column"] = col_result

        # 5. Explain via phi3.5
        explanation = await explain_anomalies({
            "table":     table,
            "type":      "Full Anomaly Analysis (Timeseries + Column Z-Score)",
            "summary":   {
                "timeseries_anomalies": results.get("timeseries", {}).get("anomaly_count", "N/A"),
                "column_outliers":      results.get("column", {}),
            },
            "anomalies": results.get("timeseries", {}).get("anomalies", [])[:5],
        })

        return {**state, "output": explanation, "raw_results": results}

    except Exception as e:
        return {**state, "output": f"Analysis failed: {str(e)}"}