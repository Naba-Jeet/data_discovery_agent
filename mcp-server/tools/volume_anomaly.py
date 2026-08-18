"""
Volume Anomaly Detection Tool
Feature 1 — Trend variance (week/month/quarter): flags > threshold %
Feature 2 — Spike/Dip classification + duplicate detection by grain
"""
import json
from db.connection import get_pool


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_date_column(conn, schema_name: str, table_name: str) -> str | None:
    """Auto-discover the first timestamp/date column in the table."""
    row = await conn.fetchrow("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = $1
          AND table_name   = $2
          AND data_type IN (
              'date',
              'timestamp without time zone',
              'timestamp with time zone'
          )
        ORDER BY ordinal_position
        LIMIT 1;
    """, schema_name, table_name)
    return row["column_name"] if row else None


def _lookback(granularity: str) -> int:
    return {"day": 7, "week": 4, "month": 3, "quarter": 4}.get(granularity, 7)


# ── Feature 1: Trend Variance ─────────────────────────────────────────────────

async def check_volume_trend(
    conn,
    schema_name: str,
    table_name: str,
    date_col: str,
    granularity: str = "week",
    threshold_pct: float = 30.0,
) -> list[dict]:
    """
    DATE_TRUNC by granularity, rolling window AVG, flag variance > threshold.
    Returns list of anomalous periods.
    """
    lookback = _lookback(granularity)
    full_table = f'"{schema_name}"."{table_name}"'

    sql = f"""
        WITH period_counts AS (
            SELECT
                DATE_TRUNC('{granularity}', "{date_col}") AS period,
                COUNT(*)                                    AS row_count
            FROM {full_table}
            GROUP BY 1
        ),
        windowed AS (
            SELECT
                period,
                row_count,
                ROUND(AVG(row_count) OVER (
                    ORDER BY period
                    ROWS BETWEEN {lookback} PRECEDING AND 1 PRECEDING
                )::numeric, 2) AS avg_prev,
                ROUND(STDDEV(row_count) OVER (
                    ORDER BY period
                    ROWS BETWEEN {lookback} PRECEDING AND 1 PRECEDING
                )::numeric, 2) AS stddev_prev
            FROM period_counts
        ),
        flagged AS (
            SELECT
                period::text,
                row_count,
                avg_prev,
                stddev_prev,
                ROUND(
                    ((row_count - avg_prev) / NULLIF(avg_prev, 0) * 100)::numeric, 2
                ) AS variance_pct,
                CASE
                    WHEN avg_prev IS NULL THEN 'INSUFFICIENT_DATA'
                    WHEN (row_count - avg_prev) / NULLIF(avg_prev, 0) >  ($1 / 100.0) THEN 'SPIKE'
                    WHEN (row_count - avg_prev) / NULLIF(avg_prev, 0) < -($1 / 100.0) THEN 'DIP'
                    ELSE 'NORMAL'
                END AS status
            FROM windowed
        )
        SELECT * FROM flagged
        ORDER BY period DESC;
    """

    rows = await conn.fetch(sql, threshold_pct)
    results = []
    for r in rows:
        results.append({
            "period":       r["period"],
            "row_count":    r["row_count"],
            "avg_prev":     float(r["avg_prev"]) if r["avg_prev"] is not None else None,
            "stddev_prev":  float(r["stddev_prev"]) if r["stddev_prev"] is not None else None,
            "variance_pct": float(r["variance_pct"]) if r["variance_pct"] is not None else None,
            "status":       r["status"],
        })
    return results


# ── Feature 2a: Spike / Dip classifier summary ───────────────────────────────

def classify_trend_results(trend_results: list[dict]) -> dict:
    """Summarise spike/dip/normal counts and compute signed metrics."""
    spikes = [r for r in trend_results if r["status"] == "SPIKE"]
    dips   = [r for r in trend_results if r["status"] == "DIP"]
    normal = [r for r in trend_results if r["status"] == "NORMAL"]

    return {
        "total_periods":  len(trend_results),
        "spikes":         len(spikes),
        "dips":           len(dips),
        "normal":         len(normal),
        "max_spike_pct":  max((r["variance_pct"] for r in spikes), default=None),
        "max_dip_pct":    min((r["variance_pct"] for r in dips),   default=None),
        "anomalous_periods": [
            r for r in trend_results if r["status"] in ("SPIKE", "DIP")
        ],
    }


# ── Feature 2b: Duplicate detection by grain columns ─────────────────────────

async def check_duplicates_by_grain(
    conn,
    schema_name: str,
    table_name: str,
    grain_cols: list[str] | None = None,
) -> dict:
    """
    Detect duplicate records based on grain columns.
    If grain_cols is None, auto-uses primary key columns.
    """
    full_table = f'"{schema_name}"."{table_name}"'

    # Auto-discover PK if no grain supplied
    if not grain_cols:
        pk_rows = await conn.fetch("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
               AND tc.table_schema    = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema    = $1
              AND tc.table_name      = $2
            ORDER BY kcu.ordinal_position;
        """, schema_name, table_name)
        grain_cols = [r["column_name"] for r in pk_rows]

    if not grain_cols:
        return {"error": "No grain columns found or supplied — cannot check duplicates."}

    col_expr = ", ".join(f'"{c}"' for c in grain_cols)

    dup_sql = f"""
        SELECT {col_expr}, COUNT(*) AS dup_count
        FROM {full_table}
        GROUP BY {col_expr}
        HAVING COUNT(*) > 1
        ORDER BY dup_count DESC
        LIMIT 50;
    """
    rows = await conn.fetch(dup_sql)
    total_dup_rows = await conn.fetchval(f"""
        SELECT COALESCE(SUM(cnt - 1), 0) FROM (
            SELECT COUNT(*) AS cnt
            FROM {full_table}
            GROUP BY {col_expr}
            HAVING COUNT(*) > 1
        ) s
    """)

    return {
        "grain_cols":       grain_cols,
        "duplicate_groups": len(rows),
        "extra_rows":       int(total_dup_rows),
        "severity":         "CRITICAL" if total_dup_rows > 0 else "OK",
        "sample":           [dict(r) for r in rows[:10]],
    }


# ── Orchestrator — MCP entry point ───────────────────────────────────────────

async def detect_volume_anomalies(
    schema_name: str,
    table_name: str,
    granularity: str = "week",
    threshold_pct: float = 30.0,
    grain_cols: str = "",          # comma-separated column names, optional
    date_col: str = "",            # override auto-discovery
) -> str:
    """
    Runs all volume anomaly checks and returns merged JSON.
    granularity: day | week | month | quarter
    threshold_pct: variance % to flag (default 30)
    grain_cols: comma-separated cols for duplicate check (auto = PK)
    date_col: override auto date column discovery
    """
    pool = await get_pool()
    parsed_grain = [c.strip() for c in grain_cols.split(",") if c.strip()] if grain_cols else None

    async with pool.acquire() as conn:
        # Resolve date column
        resolved_date_col = date_col.strip() or await _get_date_column(conn, schema_name, table_name)

        trend_results   = []
        trend_summary   = {}
        duplicate_result = {}

        if resolved_date_col:
            trend_results = await check_volume_trend(
                conn, schema_name, table_name,
                resolved_date_col, granularity, threshold_pct
            )
            trend_summary = classify_trend_results(trend_results)
        else:
            trend_summary = {"error": "No date/timestamp column found — trend analysis skipped."}

        duplicate_result = await check_duplicates_by_grain(
            conn, schema_name, table_name, parsed_grain
        )

    return json.dumps({
        "schema":           schema_name,
        "table":            table_name,
        "date_column":      resolved_date_col,
        "granularity":      granularity,
        "threshold_pct":    threshold_pct,
        "trend_analysis":   trend_results,
        "trend_summary":    trend_summary,
        "duplicate_check":  duplicate_result,
    }, indent=2, default=str)