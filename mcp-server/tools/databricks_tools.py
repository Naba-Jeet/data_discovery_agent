import os, re
from databricks import sql

DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "")
DATABRICKS_HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH", "")

def _sanitize(text: str) -> str:
    """Strip all non-ASCII and invisible Unicode characters."""
    return re.sub(r'[^\x20-\x7E]', '', text).strip()

def _wrap_query(sql: str, limit: int) -> str:
    sql = sql.strip().rstrip(";")
    # Don't wrap aggregation/analytical queries — subquery breaks alias resolution
    skip_keywords = ["group by", "order by", "limit", "having", "union", "with ", "describe", "desc ", "show "]
    if any(kw in sql.lower() for kw in skip_keywords):
        return sql
    return f"SELECT * FROM ({sql}) _q LIMIT {limit}"

def tool_query_databricks(query: str, token: str, limit: int = 100) -> dict:
    """Execute a read-only SQL query against Databricks SQL Warehouse."""
    clean_query = _sanitize(query).rstrip(";")
    clean_token = _sanitize(token)
    clean_host  = _sanitize(DATABRICKS_HOST)
    clean_path  = _sanitize(DATABRICKS_HTTP_PATH)

    print(f"DEBUG host={clean_host!r} path={clean_path!r} query={clean_query!r}")

    wrapped = _wrap_query(clean_query, limit)

    with sql.connect(
        server_hostname=clean_host,
        http_path=clean_path,
        access_token=clean_token,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(wrapped)
            cols = [d[0] for d in cursor.description]
            rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
            return {
                "rows": rows,
                "columns": cols,
                "row_count": len(rows),
                "count": len(rows)
            }