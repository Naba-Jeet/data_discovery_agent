"""
FastMCP SSE client — connects to mcp_server via SSE transport and invokes tools
using the proper MCP protocol (not plain HTTP REST).
"""
from fastmcp import Client
from fastmcp.client.transports import SSETransport

from config import MCP_SERVER_URL


def _sse_url() -> str:
    return f"{MCP_SERVER_URL}/sse"


def _unwrap(result) -> str:
    """
    Unwrap FastMCP CallToolResult → plain string.
    Handles: CallToolResult, list[TextContent], TextContent, str.
    """
    # CallToolResult has a .content attribute
    if hasattr(result, "content"):
        result = result.content
    # list of TextContent
    if isinstance(result, list) and result:
        item = result[0]
        return item.text if hasattr(item, "text") else str(item)
    # bare TextContent
    if hasattr(result, "text"):
        return result.text
    return str(result)


async def call_tool(tool_name: str, params: dict) -> str:
    """Generic MCP tool caller over SSE. Always returns a plain string."""
    async with Client(SSETransport(_sse_url())) as client:
        result = await client.call_tool(tool_name, params)
        return _unwrap(result)


# ── Typed helpers matching exact server tool signatures ──────────────────────

async def get_schema(schema_name: str = "public"):
    return await call_tool("tool_get_schema_metadata", {"schema_name": schema_name})


async def run_query(sql: str, limit: int = 100):
    return await call_tool("tool_query_remote_postgres", {"sql": sql, "limit": limit})


async def detect_anomalies(schema_name: str, table_name: str):
    return await call_tool("tool_detect_anomalies", {"schema_name": schema_name, "table_name": table_name})


async def nl_to_sql(schema_name: str, question: str):
    return await call_tool("tool_nl_to_sql", {"schema_name": schema_name, "question": question})


async def format_output(data: str, fmt: str = "json"):
    return await call_tool("tool_format_output", {"data": data, "fmt": fmt})


async def run_dq_checks(schema_name: str, table_name: str) -> str:
    return await call_tool("tool_run_dq_checks", {
        "schema_name": schema_name,
        "table_name": table_name,
    })


async def add_dq_rule(schema_name: str, table_name: str, rule_type: str,
                      column_name: str = "", parameters: str = "{}", severity: str = "warn") -> str:
    return await call_tool("tool_add_dq_rule", {
        "schema_name": schema_name,
        "table_name": table_name,
        "rule_type": rule_type,
        "column_name": column_name,
        "parameters": parameters,
        "severity": severity,
    })


async def get_dq_rules(schema_name: str, table_name: str) -> str:
    return await call_tool("tool_get_dq_rules", {
        "schema_name": schema_name,
        "table_name": table_name,
    })