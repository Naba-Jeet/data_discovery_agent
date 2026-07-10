async def run(conn, schema: str, table: str, column: str, params: dict) -> dict:
    min_val = params.get("min")
    max_val = params.get("max")

    conditions = []
    if min_val is not None:
        conditions.append(f'"{column}" < {min_val}')
    if max_val is not None:
        conditions.append(f'"{column}" > {max_val}')

    if not conditions:
        return {
            "rule_type": "range",
            "column": column,
            "status": "pass",
            "actual_value": 0,
            "expected_value": 0,
            "details": {"info": "No range bounds defined"},
        }

    where_clause = " OR ".join(conditions)
    sql = f"""
        SELECT COUNT(*) AS violations
        FROM {schema}.{table}
        WHERE {where_clause}
    """
    row = await conn.fetchrow(sql)
    violations = row["violations"]

    status = "pass" if violations == 0 else "fail"
    return {
        "rule_type": "range",
        "column": column,
        "status": status,
        "actual_value": violations,
        "expected_value": 0,
        "details": {"violations": violations, "min": min_val, "max": max_val},
    }