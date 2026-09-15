import os
from databricks import sql

DATABRICKS_HOST     = os.getenv("DATABRICKS_HOST")
DATABRICKS_HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH")


def tool_query_databricks(query: str, token: str, limit: int = 100) -> dict:
    """Execute a read-only SQL query against Databricks SQL Warehouse."""
    safe_query = query.rstrip(";")
    wrapped = f"SELECT * FROM ({safe_query}) _q LIMIT {limit}"

    with sql.connect(
        server_hostname=DATABRICKS_HOST.replace("https://", ""),
        http_path=DATABRICKS_HTTP_PATH,
        access_token=token,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(wrapped)
            cols = [d[0] for d in cursor.description]
            rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

    return {"rows": rows, "count": len(rows)}