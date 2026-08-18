async def run(conn, schema: str, table: str, column: str, params: dict) -> dict:
    sql = f"""
        SELECT
            COUNT(*) AS total,
            COUNT(DISTINCT "{column}") AS unique_count
        FROM {schema}.{table}
    """
    row = await conn.fetchrow(sql)
    total = row["total"]
    unique_count = row["unique_count"]
    duplicates = total - unique_count

    status = "pass" if duplicates == 0 else "fail"
    return {
        "rule_type": "unique",
        "column": column,
        "status": status,
        "actual_value": duplicates,
        "expected_value": 0,
        "details": {
            "total": total,
            "unique_count": unique_count,
            "duplicates": duplicates
        },
    }