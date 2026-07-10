async def run(conn, schema: str, table: str, column: str, params: dict) -> dict:
    """
    User-defined SQL assertion.
    params: {"sql": "SELECT COUNT(*) FROM sales.customer WHERE customerid IS NULL", "expect": 0}
    The SQL must return a single numeric value.
    """
    sql = params.get("sql", "")
    expect = params.get("expect", 0)

    if not sql:
        return {
            "rule_type": "custom",
            "column": column,
            "status": "fail",
            "actual_value": None,
            "expected_value": expect,
            "details": {"error": "No SQL provided"},
        }

    try:
        row = await conn.fetchrow(sql)
        actual = float(list(row.values())[0])
        status = "pass" if actual == expect else "fail"
        return {
            "rule_type": "custom",
            "column": column,
            "status": status,
            "actual_value": actual,
            "expected_value": expect,
            "details": {"sql": sql},
        }
    except Exception as e:
        return {
            "rule_type": "custom",
            "column": column,
            "status": "fail",
            "actual_value": None,
            "expected_value": expect,
            "details": {"error": str(e)},
        }