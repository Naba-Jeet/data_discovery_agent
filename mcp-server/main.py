import asyncio, json, os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP
from db.connection import close_pool
from tools.schema_tools import get_schema_metadata
from tools.query_tools import query_remote_postgres
from tools.anomaly_tools import detect_anomalies
from tools.formatter import format_output
from tools.nl_to_sql import nl_to_sql 
from tools.volume_anomaly import detect_volume_anomalies
from tools.row_anomaly import detect_row_anomaly

load_dotenv()

mcp = FastMCP(
    name="data-agent-mcp", port = 7001, host = "0.0.0.0", debug = True
)

# ── Register MCP Tools ──────────────────────────────────────

from tools.dq_tools import tool_run_dq_checks, tool_add_dq_rule, tool_get_dq_rules
from tools.databricks_tools import tool_query_databricks

mcp.add_tool(tool_run_dq_checks)
mcp.add_tool(tool_add_dq_rule)
mcp.add_tool(tool_get_dq_rules)
mcp.add_tool(tool_query_databricks)

@mcp.tool()
async def tool_get_schema_metadata(schema_name: str) -> str:
    """Get all tables, columns, types and row counts for a schema."""
    return await get_schema_metadata(schema_name)

@mcp.tool()
async def tool_query_remote_postgres(sql: str, limit: int = 100) -> str:
    """Execute a read-only SQL query and return results as JSON."""
    return await query_remote_postgres(sql, limit)

@mcp.tool()
async def tool_detect_anomalies(schema_name: str, table_name: str) -> str:
    """Run anomaly detection checks on a specific table."""
    return await detect_anomalies(schema_name, table_name)

@mcp.tool()
async def tool_format_output(data: str, fmt: str = "json") -> str:
    """Format output as 'json' or 'markdown'."""
    return format_output(data, fmt)

@mcp.tool()
async def tool_nl_to_sql(schema_name: str, question: str) -> str:
    """Convert a natural language question to SQL using local LLM and schema context."""
    return await nl_to_sql(schema_name, question)

@mcp.tool()
async def tool_detect_volume_anomalies(
    schema_name: str,
    table_name: str,
    granularity: str = "week",
    threshold_pct: float = 30.0,
    grain_cols: str = "",
    date_col: str = "",
) -> str:
    """Detect volume trend anomalies (spikes/dips) and duplicates on a table."""
    return await detect_volume_anomalies(
        schema_name, table_name, granularity, threshold_pct, grain_cols, date_col
    )

@mcp.tool(name="tool_detect_row_anomaly")
async def tool_detect_row_anomaly(
    schema_name: str,
    table_name: str,
    frequency: str,
    date_column: str = "",
    lookback_periods: int = 0,
    threshold_pct: float = 30.0,
) -> str:
    """
    Detects row-count SPIKEs and DIPs for a table bucketed by frequency.
    No stddev/variance — purely average-based deviation.

    Args:
        schema_name      : PostgreSQL schema (e.g. 'sales')
        table_name       : Table to analyse (e.g. 'salesorderheader')
        frequency        : daily | weekly | monthly | quarterly | yearly
        date_column      : Optional. Auto-resolved from schema_memory if omitted.
        lookback_periods : Periods to look back. Uses frequency default if 0.
        threshold_pct    : % deviation threshold to flag SPIKE/DIP. Default 30.
    """

    result = await detect_row_anomaly(
        schema_name=schema_name,
        table_name=table_name,
        frequency=frequency,
        date_column=date_column,
        lookback_periods=lookback_periods,
        threshold_pct=threshold_pct,
    )
    return json.dumps(result, default=str)
# ── Run ─────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport = "sse")