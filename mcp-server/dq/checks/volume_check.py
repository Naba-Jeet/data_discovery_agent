async def run(conn, schema: str, table: str, column: str, params: dict) -> dict:
    min_rows = params.get("min_rows", 1)
    max_drop_pct = params.get("max_drop_pct", 0.4)  # 40% drop threshold

    sql = f"SELECT COUNT(*) AS total FROM {schema}.{table}"
    row = await conn.fetchrow(sql)
    total = row["total"]

    status = "pass" if total >= min_rows else "fail"
    return {
        "rule_type": "volume",
        "column": None,
        "status": status,
        "actual_value": total,
        "expected_value": min_rows,
        "details": {"row_count": total, "min_rows": min_rows},
    }