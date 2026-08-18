import json
from dq.connection import get_dq_conn, DQ_DSN


async def save_results(schema: str, table: str, results: list[dict], rule_ids: list[int]):
    conn = await get_dq_conn()
    try:
        for result, rule_id in zip(results, rule_ids):
            await conn.execute(
                """
                INSERT INTO dq_results
                    (rule_id, schema_name, table_name, column_name, rule_type,
                     status, actual_value, expected_value, details)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                """,
                rule_id,
                schema,
                table,
                result.get("column"),
                result.get("rule_type"),
                result.get("status"),
                result.get("actual_value"),
                result.get("expected_value"),
                json.dumps(result.get("details", {})),
            )
    finally:
        await conn.close()


async def save_score(schema: str, table: str, results: list[dict]):
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    warned = sum(1 for r in results if r["status"] == "warn")
    score = round((passed / total) * 100, 2) if total else 0.0

    conn = await get_dq_conn()
    try:
        await conn.execute(
            """
            INSERT INTO dq_scores
                (schema_name, table_name, score, total_rules, passed, failed, warned)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            """,
            schema, table, score, total, passed, failed, warned,
        )
    finally:
        await conn.close()

    return score


async def get_rules(schema: str, table: str) -> list[dict]:
    conn = await get_dq_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT id, column_name, rule_type, parameters, severity
            FROM dq_rules
            WHERE schema_name=$1 AND table_name=$2 AND is_active=true
            """,
            schema, table,
        )
        print(f"DEBUG get_rules rows: {rows}")
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def add_rule(schema: str, table: str, column: str, rule_type: str,
                   parameters: dict, severity: str) -> int:
    conn = await get_dq_conn()
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO dq_rules
                (schema_name, table_name, column_name, rule_type, parameters, severity, is_active)
            VALUES ($1,$2,$3,$4,$5,$6,true)
            RETURNING id
            """,
            schema, table, column, rule_type, json.dumps(parameters), severity,
        )
        return row["id"]
    finally:
        await conn.close()