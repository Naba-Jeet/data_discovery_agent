"""
MCP tools for DQ Validation Engine.
"""
import json
from dq.engine import run_dq_checks
from dq.store import add_rule, get_rules


async def tool_run_dq_checks(schema_name: str, table_name: str) -> str:
    """Run all active DQ rules for a table and return scored report."""
    result = await run_dq_checks(schema_name, table_name)
    return json.dumps(result, default=str)


async def tool_add_dq_rule(
    schema_name: str,
    table_name: str,
    rule_type: str,
    column_name: str = "",
    parameters: str = "{}",
    severity: str = "warn",
) -> str:
    """Add a DQ rule for a table. rule_type: null|unique|freshness|volume|range|custom"""
    try:
        params = json.loads(parameters)
    except Exception:
        params = {}
    rule_id = await add_rule(schema_name, table_name, column_name or None, rule_type, params, severity)
    return json.dumps({"rule_id": rule_id, "status": "created"})


async def tool_get_dq_rules(schema_name: str, table_name: str) -> str:
    """Get all active DQ rules for a table."""
    rules = await get_rules(schema_name, table_name)
    return json.dumps(rules, default=str)