"""
Row-Count Anomaly Detection Tool
---------------------------------
Detects SPIKEs and DIPSs in row counts bucketed by a user-defined frequency.
No stddev/variance — purely average-based deviation.

Resolution order for date_column:
  1. User-provided (explicit)
  2. schema_memory lookup (pgvector DB)
  3. Live schema discovery via tool_get_schema_metadata
  4. Error — no date column found
"""

import json
import os
import asyncpg
from dotenv import load_dotenv
from tools.schema_tools import get_schema_metadata

load_dotenv()

# ── pgvector DB connection (data_discovery) ───────────────────────────────────
_VECTOR_DSN = (
    f"postgresql://{os.getenv('VECTOR_DB_USER', 'postgres')}:"
    f"{os.getenv('VECTOR_DB_PASSWORD', 'postgres')}@"
    f"{os.getenv('VECTOR_DB_HOST', 'localhost')}:"
    f"{os.getenv('VECTOR_DB_PORT', '5433')}/"
    f"{os.getenv('VECTOR_DB_NAME', 'data_discovery')}"
)

# ── Source DB connection (Adventureworks) ─────────────────────────────────────
_SOURCE_DSN = (
    f"postgresql://{os.getenv('CLIENT_PG_USER', 'postgres')}:"
    f"{os.getenv('CLIENT_PG_PASSWORD', 'postgres')}@"
    f"{os.getenv('CLIENT_PG_HOST', 'localhost')}:"
    f"{os.getenv('CLIENT_PG_PORT', '5432')}/"
    f"{os.getenv('CLIENT_PG_DB', 'Adventureworks')}"
)

# ── Frequency config ──────────────────────────────────────────────────────────
_FREQ_CONFIG = {
    "daily":     {"trunc": "day",     "unit": "days",   "fmt": "YYYY-MM-DD",    "default_lookback": 30},
    "weekly":    {"trunc": "week",    "unit": "weeks",  "fmt": 'YYYY-"W"IW',    "default_lookback": 12},
    "monthly":   {"trunc": "month",   "unit": "months", "fmt": "YYYY-MM",       "default_lookback": 12},
    "quarterly": {"trunc": "quarter", "unit": "months", "fmt": 'YYYY-"Q"Q',     "default_lookback": 8,  "unit_multiplier": 3},
    "yearly":    {"trunc": "year",    "unit": "years",  "fmt": "YYYY",          "default_lookback": 5},
}

# Date column name priority (lower index = higher priority)
_DATE_COL_PRIORITY = ["created_at", "updated_at"]
_DATE_COL_PATTERNS = ["date", "time", "at"]   # substring match fallback
_DATE_TYPES        = {"timestamp without time zone", "timestamp with time zone",
                      "date", "timestamptz", "timestamp"}


# ── Date column resolution ────────────────────────────────────────────────────

def _pick_date_column(columns: list[dict]) -> str | None:
    """
    Given a list of column dicts {name, type}, return the best date column.
    Priority: named exact → pattern match → first date-typed.
    """
    date_cols = [c for c in columns if c.get("type", "").lower() in _DATE_TYPES]
    if not date_cols:
        return None

    # Priority 1 — exact name match
    for priority_name in _DATE_COL_PRIORITY:
        for col in date_cols:
            if col["name"].lower() == priority_name:
                return col["name"]

    # Priority 2 — substring pattern match
    for pattern in _DATE_COL_PATTERNS:
        for col in date_cols:
            if pattern in col["name"].lower():
                return col["name"]

    # Priority 3 — first date-typed column
    return date_cols[0]["name"]


async def _resolve_date_column(
    schema_name: str,
    table_name: str,
    user_provided: str | None,
) -> tuple[str, str]:
    """
    Returns (date_column, source) where source is:
      'user_provided' | 'schema_memory' | 'live_discovery'
    Raises ValueError if no date column found.
    """

    # 1. User provided
    if user_provided:
        return user_provided, "user_provided"

    # 2. schema_memory (pgvector DB)
    try:
        pool = await asyncpg.create_pool(_VECTOR_DSN, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT metadata FROM schema_memory WHERE schema_name=$1 AND table_name=$2",
                schema_name, table_name
            )
        await pool.close()

        if row and row["metadata"]:
            meta = row["metadata"]
            columns = meta if isinstance(meta, list) else meta.get("columns", [])
            picked = _pick_date_column(columns)
            if picked:
                return picked, "schema_memory"
    except Exception:
        pass  # fall through to live discovery

    # 3. Live discovery via schema tool
    raw = await get_schema_metadata(schema_name)
    schema_data = json.loads(raw)
    table_meta  = schema_data.get(table_name, schema_data.get(table_name.lower()))

    if not table_meta:
        raise ValueError(f"Table '{table_name}' not found in schema '{schema_name}'.")

    columns = table_meta if isinstance(table_meta, list) else table_meta.get("columns", [])
    picked  = _pick_date_column(columns)

    if not picked:
        raise ValueError(
            f"No date/timestamp column found in '{schema_name}.{table_name}'. "
            "Pass 'date_column' explicitly."
        )

    return picked, "live_discovery"


# ── SQL builder ───────────────────────────────────────────────────────────────

def _build_sql(
    schema_name: str,
    table_name: str,
    date_col: str,
    freq: str,
    lookback: int,
    threshold_pct: float,
) -> str:
    cfg         = _FREQ_CONFIG[freq]
    trunc       = cfg["trunc"]
    unit        = cfg["unit"]
    date_fmt    = cfg["fmt"]
    multiplier  = cfg.get("unit_multiplier", 1)
    interval_n  = lookback * multiplier

    return f"""
WITH bucketed AS (
    SELECT
        DATE_TRUNC('{trunc}', {date_col}::timestamp) AS period,
        COUNT(*)                                      AS row_count
    FROM {schema_name}.{table_name}
    WHERE {date_col} >= (SELECT MAX({date_col}) FROM {schema_name}.{table_name}) - INTERVAL '{interval_n} {unit}'
    GROUP BY 1
),
averaged AS (
    SELECT
        period,
        row_count,
        AVG(row_count) OVER (
            ORDER BY period
            ROWS BETWEEN {lookback} PRECEDING AND 1 PRECEDING
        ) AS rolling_avg
    FROM bucketed
),
flagged AS (
    SELECT
        TO_CHAR(period, '{date_fmt}')                                                      AS period,
        row_count,
        ROUND(rolling_avg::numeric, 2)                                                     AS rolling_avg,
        ROUND(
            ((row_count - rolling_avg) / NULLIF(rolling_avg, 0) * 100)::numeric, 2
        )                                                                                  AS deviation_pct,
        CASE
            WHEN (row_count - rolling_avg) / NULLIF(rolling_avg, 0) * 100 >  {threshold_pct} THEN 'SPIKE'
            WHEN (row_count - rolling_avg) / NULLIF(rolling_avg, 0) * 100 < -{threshold_pct} THEN 'DIP'
            ELSE 'NORMAL'
        END                                                                                AS flag
    FROM averaged
)
SELECT * FROM flagged
ORDER BY
    CASE flag WHEN 'SPIKE' THEN 1 WHEN 'DIP' THEN 2 ELSE 3 END,
    deviation_pct DESC NULLS LAST;
""".strip()

# ── Executor ──────────────────────────────────────────────────────────────────

async def _run_sql(sql: str) -> list[dict]:
    pool = await asyncpg.create_pool(_SOURCE_DSN, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql)
        return [dict(r) for r in rows]
    finally:
        await pool.close()


# ── Main tool entry point ─────────────────────────────────────────────────────

async def detect_row_anomaly(
    schema_name: str,
    table_name: str,
    frequency: str,
    date_column: str = "",
    lookback_periods: int = 0,
    threshold_pct: float = 30.0,
) -> dict:
    """
    Detects row-count SPIKEs and DIPs for a table over a given frequency.

    Args:
        schema_name      : PostgreSQL schema (e.g. 'sales')
        table_name       : Table to analyse (e.g. 'salesorderheader')
        frequency        : 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly'
        date_column      : Optional. If empty, auto-resolved from schema memory.
        lookback_periods : Number of periods to look back. Defaults per frequency.
        threshold_pct    : % deviation to flag as SPIKE/DIP. Default 30.
    """

    # Validate frequency
    frequency = frequency.lower().strip()
    if frequency not in _FREQ_CONFIG:
        return {"error": f"Invalid frequency '{frequency}'. Choose from: {list(_FREQ_CONFIG.keys())}"}

    cfg      = _FREQ_CONFIG[frequency]
    lookback = lookback_periods if lookback_periods > 0 else cfg["default_lookback"]

    # Resolve date column
    try:
        date_col, date_col_source = await _resolve_date_column(
            schema_name, table_name, date_column or None
        )
    except ValueError as e:
        return {"error": str(e)}

    # Build + execute SQL
    sql = _build_sql(schema_name, table_name, date_col, frequency, lookback, threshold_pct)

    try:
        rows = await _run_sql(sql)
    except Exception as e:
        return {"error": str(e), "sql": sql}

    # Summarise
    spikes  = [r for r in rows if r.get("flag") == "SPIKE"]
    dips    = [r for r in rows if r.get("flag") == "DIP"]
    normals = [r for r in rows if r.get("flag") == "NORMAL"]

    summary = (
        f"{len(spikes) + len(dips)} anomalies detected over {lookback} {frequency} periods "
        f"({len(spikes)} SPIKE, {len(dips)} DIP, {len(normals)} NORMAL). "
        f"Threshold: ±{threshold_pct}%."
    )

    return {
        "meta": {
            "schema":            schema_name,
            "table":             table_name,
            "date_column":       date_col,
            "date_column_source": date_col_source,
            "frequency":         frequency,
            "lookback_periods":  lookback,
            "threshold_pct":     threshold_pct,
            "sql":               sql,
        },
        "anomalies_found": len(spikes) + len(dips),
        "summary":         summary,
        "result":          rows,
    }