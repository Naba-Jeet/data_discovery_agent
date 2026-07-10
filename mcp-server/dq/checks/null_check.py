async def run(conn, schema: str, table: str, column: str, params: dict) -> dict:
    threshold = params.get("threshold", 0.05)  # 5% nulls allowed by default

    sql = f"""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE "{column}" IS NULL) AS null_count
        FROM {schema}.{table}
    """
    row = await conn.fetchrow(sql)
    total = row["total"] or 1
    null_count = row["null_count"]
    null_ratio = null_count / total

    status = "pass" if null_ratio <= threshold else "fail"
    return {
        "rule_type": "null",
        "column": column,
        "status": status,
        "actual_value": round(null_ratio, 4),
        "expected_value": threshold,
        "details": {
            "total": total,
            "null_count": null_count,
            "null_ratio": null_ratio
        },
    }