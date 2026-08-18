async def run(conn, schema: str, table: str, column: str, params: dict) -> dict:
    max_age_hours = params.get("max_age_hours", 24)
    sql = f"""
        SELECT MAX("{column}") AS latest
        FROM {schema}.{table}
    """
    row = await conn.fetchrow(sql)
    latest = row["latest"]

    if latest is None:
        return {
            "rule_type": "freshness",
            "column": column,
            "status": "fail",
            "actual_value": None,
            "expected_value": max_age_hours,
            "details": {"error": "No data found"},
        }

    sql_age = f"""
        SELECT EXTRACT(EPOCH FROM (now() - MAX("{column}"))) / 3600 AS age_hours
        FROM {schema}.{table}
    """
    age_row = await conn.fetchrow(sql_age)
    age_hours = float(age_row["age_hours"])

    status = "pass" if age_hours <= max_age_hours else "fail"
    return {
        "rule_type": "freshness",
        "column": column,
        "status": status,
        "actual_value": round(age_hours, 2),
        "expected_value": max_age_hours,
        "details": {"latest_value": str(latest), "age_hours": age_hours},
    }