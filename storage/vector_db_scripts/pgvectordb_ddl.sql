-- ============================================================
-- data_discovery database — DDL
-- Run against: pgvector/pgvector:0.8.5-pg18-trixie
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ────────────────────────────────────────────────────────────
-- DQ Rules Registry
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dq_rules (
    id             SERIAL PRIMARY KEY,
    schema_name    TEXT NOT NULL,
    table_name     TEXT NOT NULL,
    column_name    TEXT,                        -- NULL for table-level rules
    rule_type      TEXT NOT NULL,               -- null|unique|freshness|volume|range|custom
    parameters     JSONB,                       -- {"threshold": 0.05, "min": 0, "max": 1000}
    severity       TEXT DEFAULT 'warn',         -- warn|critical
    is_active      BOOLEAN DEFAULT true,
    created_at     TIMESTAMPTZ DEFAULT now()
);

-- ────────────────────────────────────────────────────────────
-- DQ Run Results
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dq_results (
    id             SERIAL PRIMARY KEY,
    rule_id        INT REFERENCES dq_rules(id),
    schema_name    TEXT,
    table_name     TEXT,
    column_name    TEXT,
    rule_type      TEXT,
    status         TEXT,                        -- pass|fail|warn
    actual_value   NUMERIC,
    expected_value NUMERIC,
    details        JSONB,
    run_at         TIMESTAMPTZ DEFAULT now()
);

-- ────────────────────────────────────────────────────────────
-- DQ Scores per table per run
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dq_scores (
    id             SERIAL PRIMARY KEY,
    schema_name    TEXT,
    table_name     TEXT,
    score          NUMERIC,                     -- 0-100
    total_rules    INT,
    passed         INT,
    failed         INT,
    warned         INT,
    run_at         TIMESTAMPTZ DEFAULT now()
);

-- ────────────────────────────────────────────────────────────
-- Agent Memory (pgvector — for session history + semantic retrieval)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_memory (
    id             SERIAL PRIMARY KEY,
    session_id     TEXT,
    pg_schema      TEXT,
    intent         TEXT,
    user_message   TEXT,
    generated_sql  TEXT,
    result_summary TEXT,
    embedding      vector(768),
    created_at     TIMESTAMPTZ DEFAULT now()
);

-- schema_memory
CREATE TABLE schema_memory (
    id SERIAL PRIMARY KEY,
    schema_name TEXT,
    table_name TEXT,
    metadata JSONB,
    embedding vector(384),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(schema_name, table_name)
);

-- query_memory
CREATE TABLE query_memory (
    id SERIAL PRIMARY KEY,
    intent TEXT,
    question TEXT,
    tool_result JSONB,
    sql_used TEXT,
    tables TEXT[],
    keywords TEXT[],
    embedding vector(384),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS agent_memory_embedding_idx
    ON agent_memory USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);


CREATE INDEX IF NOT EXISTS idx_schema_memory_embedding ON schema_memory USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_query_memory_embedding ON query_memory USING ivfflat (embedding vector_cosine_ops);