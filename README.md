# 🐝 Data Discovery Agent

A local-first, agentic data exploration platform powered by **LangGraph**, **FastMCP**, **pgvector**, and **Ollama**. Supports natural language queries, schema discovery, anomaly detection, and data quality validation — all running on your machine without external API calls.

---

## 🏗️ Architecture Overview

```
User Request (POST /chat)
        ↓
  FastAPI App (port 8000)
        ↓
  LangGraph Pipeline
  ┌─────────────────────────────────────────┐
  │  classify_intent                        │
  │       ↓                                 │
  │  rag_node  ←→  pgvector (schema_memory) │
  │       ↓                                 │
  │  llm_node  ←→  Ollama (nl_to_sql only)  │
  │       ↓                                 │
  │  executor_node  ←→  MCP Server (8001)   │
  │       ↓                                 │
  │  formatter_node                         │
  └─────────────────────────────────────────┘
        ↓
  MCP Server (FastMCP SSE, port 8001)
        ↓
  Source PostgreSQL (AdventureWorks)
  + data_discovery DB (pgvector, DQ rules)
```

---

## 📦 Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Runtime |
| PostgreSQL | 14+ | Source DB + metadata store |
| pgvector | 0.8+ | Vector memory |
| Ollama | Latest | Local LLM |
| Git | Any | Clone repo |

---

## 🚀 Setup — Step by Step

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/data-discovery-agent.git
cd data-discovery-agent
```

### 2. Install Ollama & Pull Model

```bash
# Install Ollama from https://ollama.com
ollama pull qwen2.5:1.5b
ollama serve   # runs on port 11434
```

### 3. Setup Source Database (AdventureWorks)

```bash
# Download AdventureWorks PostgreSQL dump
# https://github.com/lorint/AdventureWorks-for-Postgres
psql -U postgres -c "CREATE DATABASE \"Adventureworks\";"
psql -U postgres -d "Adventureworks" -f install.sql
```

### 4. Setup Metadata / DQ Database

```sql
-- Run as postgres superuser
CREATE DATABASE data_discovery;
\c data_discovery
CREATE EXTENSION IF NOT EXISTS vector;

-- DQ tables
CREATE TABLE IF NOT EXISTS dq_rules (
    id SERIAL PRIMARY KEY,
    schema_name TEXT,
    table_name TEXT,
    column_name TEXT,
    rule_type TEXT,
    parameters JSONB,
    severity TEXT DEFAULT 'warn',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dq_results (
    id SERIAL PRIMARY KEY,
    schema_name TEXT,
    table_name TEXT,
    rule_id INTEGER REFERENCES dq_rules(id),
    status TEXT,
    actual_value NUMERIC,
    expected_value NUMERIC,
    details JSONB,
    run_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dq_scores (
    id SERIAL PRIMARY KEY,
    schema_name TEXT,
    table_name TEXT,
    score NUMERIC,
    total_rules INT,
    passed INT,
    failed INT,
    warned INT,
    run_at TIMESTAMPTZ DEFAULT now()
);

-- Memory tables
CREATE TABLE IF NOT EXISTS schema_memory (
    id SERIAL PRIMARY KEY,
    schema_name TEXT,
    table_name TEXT,
    metadata JSONB,
    embedding vector(384),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(schema_name, table_name)
);

CREATE TABLE IF NOT EXISTS query_memory (
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

CREATE INDEX IF NOT EXISTS idx_schema_memory_embedding ON schema_memory USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_query_memory_embedding ON query_memory USING ivfflat (embedding vector_cosine_ops);
```

### 5. Configure Environment Variables

**`mcp_server/.env`**
```env
SOURCE_PG_HOST=localhost
SOURCE_PG_PORT=5432
SOURCE_PG_USER=postgres
SOURCE_PG_PASSWORD=your_password
SOURCE_PG_DB=Adventureworks

DD_PG_HOST=localhost
DD_PG_PORT=5433
DD_PG_USER=postgres
DD_PG_PASSWORD=your_password
DD_PG_DB=data_discovery

OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:1.5b
```

**`app/.env`**
```env
MCP_SERVER_URL=http://localhost:7001
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:1.5b
MEMORY_DSN=postgresql://postgres:your_password@localhost:5433/data_discovery
```

### 6. Install Python Dependencies

```bash
# MCP Server
cd mcp_server
pip install -r requirements.txt

# App
cd ../app
pip install -r requirements.txt
pip install sentence-transformers pgvector
```

**`mcp_server/requirements.txt`**
```
fastmcp>=0.4.0
asyncpg
httpx
python-dotenv
sqlglot
```

**`app/requirements.txt`**
```
fastapi
uvicorn
langgraph
langchain-core
httpx
asyncpg
fastmcp>=0.4.0
python-dotenv
sentence-transformers>=2.7.0
pgvector>=0.3.0
```

---

## ▶️ Running the Stack

Open **3 separate terminals**:

**Terminal 1 — Ollama**
```bash
ollama serve
```

**Terminal 2 — MCP Server**
```bash
cd mcp_server
python main.py
# Running on http://localhost:8001
```

**Terminal 3 — App**
```bash
cd app
python main.py
# Running on http://localhost:8000
```

---

## 🔌 API Reference

All requests go to `POST http://localhost:8000/chat`

### Request Schema

```json
{
  "message": "your natural language question",
  "pg_schema": "sales"
}
```

---

### 1. 📋 Schema Discovery

Discover tables and columns in a schema.

```powershell
$r = Invoke-RestMethod -Uri "http://localhost:8000/chat" `
  -Method POST -ContentType "application/json" `
  -Body '{"message":"describe tables in sales schema","pg_schema":"sales"}'
$r.final_response
```

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"describe tables in sales schema","pg_schema":"sales"}'
```

**Response:** Markdown table of all tables with column names.

---

### 2. 🧠 Natural Language → SQL

Convert a plain English question into SQL and execute it.

```powershell
# Simple count
$r = Invoke-RestMethod -Uri "http://localhost:8000/chat" `
  -Method POST -ContentType "application/json" `
  -Body '{"message":"how many orders are in salesorderheader","pg_schema":"sales"}'
$r.final_response

# Aggregation
$r = Invoke-RestMethod -Uri "http://localhost:8000/chat" `
  -Method POST -ContentType "application/json" `
  -Body '{"message":"find total subtotal from salesorderheader","pg_schema":"sales"}'
$r.final_response

# Group by
$r = Invoke-RestMethod -Uri "http://localhost:8000/chat" `
  -Method POST -ContentType "application/json" `
  -Body '{"message":"count orders by status in salesorderheader","pg_schema":"sales"}'
$r.final_response

# Date filter
$r = Invoke-RestMethod -Uri "http://localhost:8000/chat" `
  -Method POST -ContentType "application/json" `
  -Body '{"message":"count orders placed in year 2013 from salesorderheader","pg_schema":"sales"}'
$r.final_response

# Join query
$r = Invoke-RestMethod -Uri "http://localhost:8000/chat" `
  -Method POST -ContentType "application/json" `
  -Body '{"message":"find total orders and revenue per territory from salesorderheader","pg_schema":"sales"}'
$r.final_response
```

**Response:** Generated SQL + query results as a markdown table.

> ⚠️ **Tip:** Always include the exact table name in your question for best results with small LLMs.

---

### 3. 🔍 Anomaly Detection

Detect statistical anomalies (Z-score based) in numeric columns.

```powershell
$r = Invoke-RestMethod -Uri "http://localhost:8000/chat" `
  -Method POST -ContentType "application/json" `
  -Body '{"message":"detect anomalies in salesorderheader","pg_schema":"sales"}'
$r.final_response
```

**Response:** JSON with anomaly flags per column including mean, stddev, and outlier count.

---

### 4. ✅ Data Quality (DQ)

#### Add a DQ Rule

```powershell
# Null check rule
$r = Invoke-RestMethod -Uri "http://localhost:8000/chat" `
  -Method POST -ContentType "application/json" `
  -Body '{
    "message": "add dq rule",
    "pg_schema": "sales",
    "rule_type": "null",
    "column_name": "customerid",
    "parameters": "{\"threshold\": 0.01}",
    "severity": "critical"
  }'
$r.final_response

# Uniqueness check rule
$r = Invoke-RestMethod -Uri "http://localhost:8000/chat" `
  -Method POST -ContentType "application/json" `
  -Body '{
    "message": "add dq rule",
    "pg_schema": "sales",
    "rule_type": "unique",
    "column_name": "salesorderid",
    "parameters": "{}",
    "severity": "critical"
  }'
$r.final_response
```

**Supported rule types:** `null`, `unique`, `range`, `regex`, `freshness`

#### List DQ Rules

```powershell
$r = Invoke-RestMethod -Uri "http://localhost:8000/chat" `
  -Method POST -ContentType "application/json" `
  -Body '{"message":"list dq rules for salesorderheader","pg_schema":"sales"}'
$r.final_response
```

#### Run DQ Checks

```powershell
$r = Invoke-RestMethod -Uri "http://localhost:8000/chat" `
  -Method POST -ContentType "application/json" `
  -Body '{"message":"run dq checks on salesorderheader","pg_schema":"sales"}'
$r.final_response
```

**Response:**
```json
{
  "schema": "sales",
  "table": "salesorderheader",
  "score": 100.0,
  "total_rules": 4,
  "passed": 4,
  "failed": 0,
  "warned": 0,
  "results": [...]
}
```

---

## 🧠 Memory Layer (pgvector)

The agent automatically:
- **Caches schema metadata** in `schema_memory` on first discovery
- **Serves from cache** on subsequent requests (no MCP call needed)
- **Stores all successful tool results** in `query_memory` with embeddings
- **Retrieves similar past SQL** for NL→SQL to improve accuracy

Verify memory:
```sql
-- Check schema cache
SELECT schema_name, table_name, updated_at FROM schema_memory;

-- Check query history
SELECT intent, question, sql_used, created_at FROM query_memory ORDER BY created_at DESC;
```

---

## 🗂️ Project Structure

```
data-discovery-agent/
├── mcp_server/
│   ├── main.py                  # FastMCP SSE server (port 8001)
│   ├── db/
│   │   └── connection.py        # asyncpg pool (source + DD DB)
│   └── tools/
│       ├── schema_tools.py      # get_schema_metadata
│       ├── query_tools.py       # query_remote_postgres
│       ├── anomaly_tools.py     # detect_anomalies
│       ├── nl_to_sql.py         # NL→SQL via Ollama
│       ├── dq_tools.py          # add_rule, list_rules, run_checks
│       └── formatter.py         # format_output
├── app/
│   ├── main.py                  # FastAPI app (port 8000)
│   ├── config.py                # env config
│   ├── mcp_client/
│   │   └── client.py            # FastMCP SSE client
│   ├── memory/
│   │   ├── embeddings.py        # sentence-transformers (all-MiniLM-L6-v2)
│   │   └── store.py             # pgvector upsert + similarity search
│   └── agent/
│       ├── intent.py            # regex-based intent classifier
│       ├── prompt_router.py     # system prompts per intent
│       ├── orchestrator.py      # LangGraph graph definition
│       └── nodes/
│           ├── rag.py           # schema fetch + memory lookup
│           ├── llm.py           # Ollama call (nl_to_sql only)
│           ├── executor.py      # MCP tool dispatcher
│           └── formatter.py     # response renderer
└── README.md
```

---

## 🔧 Intent Routing

The agent classifies messages using regex rules:

| Intent | Trigger Keywords | Action |
|--------|-----------------|--------|
| `anomaly` | anomaly, outlier, spike, drift | → `tool_detect_anomalies` |
| `dq` | dq, data quality, validate, null check, run checks | → `tool_run_dq_checks` / `tool_add_dq_rule` |
| `nl_to_sql` | how many, what is, list, find, top N, average, count | → `tool_nl_to_sql` → execute |
| `query` | run, execute, select, fetch | → `tool_query_remote_postgres` |
| `schema` | schema, columns, metadata, describe, structure | → `tool_get_schema_metadata` |

---

## ⚠️ Known Limitations

- Small LLM (`qwen2.5:1.5b`) works best when the **exact table name** is mentioned in the question
- NL→SQL JOIN queries may require explicit table names in the message
- `?` character in PowerShell request body should be avoided (escaping issue)
- First request after startup is slower (model warm-up + schema cache population)

---

## 🗺️ Roadmap

- [ ] Docker Compose (full stack)
- [ ] Frontend UI dashboard
- [ ] Freshness / volume / schema drift monitoring
- [ ] Celery Beat scheduled metadata jobs
- [ ] Snowflake + Databricks connectors
- [ ] Auth / RBAC (OAuth2, Keycloak)
- [ ] Slack alerts
- [ ] Incident management page