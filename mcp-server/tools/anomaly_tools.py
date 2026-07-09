import json
from db.connection import get_pool

async def detect_anomalies(schema_name: str, table_name: str) -> str:
    """
    Runs a suite of anomaly detection queries on a given table.
    Returns structured findings as JSON.
    """
    pool = await get_pool()
    findings = []

    async with pool.acquire() as conn:

        # 1. Get columns
        columns = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = $1 AND table_name = $2
            ORDER BY ordinal_position;
        """, schema_name, table_name)

        if not columns:
            return json.dumps({"error": f"Table {schema_name}.{table_name} not found."})

        full_table = f'"{schema_name}"."{table_name}"'

        # 2. Total row count
        total_rows = await conn.fetchval(f"SELECT COUNT(*) FROM {full_table}")

        # 3. NULL rate per column
        for col in columns:
            col_name = col["column_name"]
            null_count = await conn.fetchval(
                f'SELECT COUNT(*) FROM {full_table} WHERE "{col_name}" IS NULL'
            )
            null_pct = round((null_count / total_rows) * 100, 2) if total_rows > 0 else 0
            if null_pct > 5:
                findings.append({
                    "check": "NULL rate",
                    "column": col_name,
                    "severity": "HIGH" if null_pct > 20 else "MEDIUM",
                    "detail": f"{null_pct}% NULL values — threshold: 5%",
                    "null_count": null_count,
                    "total_rows": total_rows
                })

        # 4. Duplicate primary key check
        pk_cols = await conn.fetch("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
            AND tc.table_schema = $1
            AND tc.table_name = $2;
        """, schema_name, table_name)

        if pk_cols:
            pk_col = pk_cols[0]["column_name"]
            dup_count = await conn.fetchval(f"""
                SELECT COUNT(*) FROM (
                    SELECT "{pk_col}", COUNT(*) as cnt
                    FROM {full_table}
                    GROUP BY "{pk_col}"
                    HAVING COUNT(*) > 1
                ) dups
            """)
            if dup_count > 0:
                findings.append({
                    "check": "Duplicate primary key",
                    "column": pk_col,
                    "severity": "CRITICAL",
                    "detail": f"{dup_count} duplicate values found in primary key column",
                    "duplicate_count": dup_count
                })

        # 5. Negative values in numeric columns
        numeric_types = ["integer", "numeric", "real", "double precision", "bigint", "smallint"]
        for col in columns:
            if col["data_type"] in numeric_types:
                col_name = col["column_name"]
                neg_count = await conn.fetchval(
                    f'SELECT COUNT(*) FROM {full_table} WHERE "{col_name}" < 0'
                )
                if neg_count > 0:
                    findings.append({
                        "check": "Negative values",
                        "column": col_name,
                        "severity": "HIGH",
                        "detail": f"{neg_count} negative values found in numeric column",
                        "negative_count": neg_count
                    })

        # 6. Future dates in date/timestamp columns
        date_types = ["date", "timestamp without time zone", "timestamp with time zone"]
        for col in columns:
            if col["data_type"] in date_types:
                col_name = col["column_name"]
                future_count = await conn.fetchval(
                    f'SELECT COUNT(*) FROM {full_table} WHERE "{col_name}" > NOW()'
                )
                if future_count > 0:
                    findings.append({
                        "check": "Future dates",
                        "column": col_name,
                        "severity": "MEDIUM",
                        "detail": f"{future_count} future-dated records found",
                        "future_count": future_count
                    })

    return json.dumps({
        "schema": schema_name,
        "table": table_name,
        "total_rows": total_rows,
        "anomalies_found": len(findings),
        "findings": findings
    }, indent=2)