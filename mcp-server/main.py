import asyncio
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP
from db.connection import close_pool
from tools.schema_tools import get_schema_metadata
from tools.query_tools import query_remote_postgres
from tools.anomaly_tools import detect_anomalies
from tools.formatter import format_output
from tools.nl_to_sql import nl_to_sql 

load_dotenv()

mcp = FastMCP(
    name="data-agent-mcp", port = 8001, host = "0.0.0.0", debug = True
)

# ── Register MCP Tools ──────────────────────────────────────

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

# ── Run ─────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport = "sse")