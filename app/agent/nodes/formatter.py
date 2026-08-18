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

def _render_volume_anomaly(tool_result: dict) -> str:
    parts = []

    summary = tool_result.get("trend_summary", {})
    dup     = tool_result.get("duplicate_check", {})
    table   = tool_result.get("table", "")
    gran    = tool_result.get("granularity", "week")
    thresh  = tool_result.get("threshold_pct", 30)
    date_col = tool_result.get("date_column", "")

    parts.append(
        f"📊 **Volume Anomaly Report** — `{table}` "
        f"| granularity: `{gran}` | threshold: `{thresh}%` | date col: `{date_col}`\n"
    )

    # ── Trend summary ────────────────────────────────────────
    if "error" in summary:
        parts.append(f"⚠️ Trend analysis skipped: {summary['error']}\n")
    else:
        parts.append(
            f"**Trend Summary:** {summary.get('total_periods',0)} periods · "
            f"🔴 Spikes: {summary.get('spikes',0)} · "
            f"🔵 Dips: {summary.get('dips',0)} · "
            f"✅ Normal: {summary.get('normal',0)}\n"
        )
        if summary.get("max_spike_pct") is not None:
            parts.append(f"↑ Max spike: `+{summary['max_spike_pct']}%`")
        if summary.get("max_dip_pct") is not None:
            parts.append(f"↓ Max dip: `{summary['max_dip_pct']}%`\n")

    # ── Anomalous periods table ──────────────────────────────
    anomalous = summary.get("anomalous_periods", [])
    if anomalous:
        parts.append("\n**🚨 Flagged Periods:**\n")
        parts.append("| Period | Row Count | Avg Prev | Variance % | Status |")
        parts.append("|--------|-----------|----------|------------|--------|")
        for r in anomalous:
            icon = "🔴" if r["status"] == "SPIKE" else "🔵"
            parts.append(
                f"| {r['period']} | {r['row_count']} | {r['avg_prev']} "
                f"| {r['variance_pct']}% | {icon} {r['status']} |"
            )
    else:
        parts.append("✅ No trend anomalies detected in flagged periods.\n")

    # ── Duplicate check ──────────────────────────────────────
    parts.append("\n**🔁 Duplicate Check:**")
    if "error" in dup:
        parts.append(f"⚠️ {dup['error']}")
    else:
        grain_str = ", ".join(f"`{c}`" for c in dup.get("grain_cols", []))
        sev_icon  = "🔴" if dup.get("severity") == "CRITICAL" else "✅"
        parts.append(
            f"{sev_icon} Grain: {grain_str} | "
            f"Duplicate groups: `{dup.get('duplicate_groups', 0)}` | "
            f"Extra rows: `{dup.get('extra_rows', 0)}`"
        )
        if dup.get("sample"):
            parts.append("\n_Sample duplicate records (top 10):_")
            sample = dup["sample"]
            if sample:
                cols = list(sample[0].keys())
                parts.append("| " + " | ".join(cols) + " |")
                parts.append("| " + " | ".join(["---"] * len(cols)) + " |")
                for row in sample:
                    parts.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")

    return "\n".join(parts)

async def formatter_node(state: dict[str, Any]) -> dict[str, Any]:
    intent = state.get("intent", "unknown")
    llm_response = state.get("llm_response", "")
    tool_result = state.get("tool_result", {})

    parts = []

    if intent == "nl_to_sql":
        sql = tool_result.get("generated_sql", "")
        if sql:
            parts.append(f"🧠 **Generated SQL:**\nsql\n{sql}\n```")
    elif llm_response:
        parts.append(llm_response)

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
                    col_str = ", ".join(f"`{c['name']}`" for c in cols)
                    lines.append(f"**{table}**: {col_str}")
                parts.append("\n".join(lines))

            elif intent == "anomaly":
                parts.append(f"\n🔍 **Anomaly Detection Result:**\n```json\n{json.dumps(tool_result, indent=2)}\n```")

            elif intent == "dq":
                parts.append(f"🔎 **DQ Result:**\n```json\n{json.dumps(tool_result, indent=2)}\n```")

            elif intent == "volume_anomaly":
                parts.append(_render_volume_anomaly(tool_result))

            else:
                parts.append(f"\n```json\n{json.dumps(tool_result, indent=2)}\n```")

        state["final_response"] = "\n".join(parts).strip()
        return state