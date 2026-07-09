import json
from db.connection import get_pool

# Safety: only allow SELECT statements
BLOCKED_KEYWORDS = ["insert", "update", "delete", "drop", "truncate", "alter", "create", "grant"]

def is_safe_query(sql: str) -> bool:

    sql = sql.replace(";", "")
    sql_lower = sql.strip().lower()
    
    if not sql_lower.startswith("select"):
        return False
    for keyword in BLOCKED_KEYWORDS:
        if keyword in sql_lower:
            return False
    return True

async def query_remote_postgres(sql: str, limit: int = 100) -> str:
    """
    Executes a read-only SQL query against the remote PostgreSQL.
    Returns results as JSON.
    """
    if not is_safe_query(sql):
        return json.dumps({
            "error": "Only SELECT queries are allowed.",
            "sql": sql
        })

    # Enforce row limit
    safe_sql = f"SELECT * FROM ({sql}) AS _q LIMIT {limit}"

    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(safe_sql)
            result = [dict(row) for row in rows]
            return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e), "sql": safe_sql})