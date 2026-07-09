import json
import httpx
import os
from tools.schema_tools import get_schema_metadata
from dotenv import load_dotenv


load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")


import re

import sqlglot

def _validate_and_fix_sql(sql: str, schema_name: str, known_tables: list) -> tuple[str, str | None]:
    # Match FROM/JOIN but skip if already schema-qualified (e.g. sales.customer)
    pattern = r'\b(?:FROM|JOIN)\s+(?:(\w+)\.)?(\w+)(?:\s+(?:AS\s+)?\w+)?'
    matches = re.findall(pattern, sql, re.IGNORECASE)

    bad = []
    for schema_part, table_part in matches:
        if schema_part.lower() == schema_name.lower():
            continue  # already qualified — skip validation
        if table_part.lower() not in [t.lower() for t in known_tables]:
            bad.append(table_part)

    if bad:
        return sql, f"Hallucinated tables: {bad}. Known tables: {[t.lower() for t in known_tables]}"
    return sql, None

def extract_sql(raw: str) -> str:
    # Strip markdown code fences
    match = re.search(r"```(?:sql)?\s*(.*?)```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: take only lines starting with SQL keywords
    lines = raw.strip().splitlines()
    sql_lines = []
    for line in lines:
        if re.match(r"^\s*(SELECT|INSERT|UPDATE|DELETE|WITH|FROM|WHERE|GROUP|ORDER|LIMIT|JOIN|HAVING)", line, re.IGNORECASE):
            sql_lines.append(line)
        elif sql_lines:  # stop at explanation text
            break
    return "\n".join(sql_lines).strip()

async def nl_to_sql(schema_name: str, question: str) -> str:
    # Step 1: fetch schema context
    schema_json = await get_schema_metadata(schema_name)

    # Get table names for post-processing
    try:
        schema_data = json.loads(schema_json)
        table_names = list(schema_data.keys())
        context_lines = []
        for table, meta in schema_data.items():
            cols = meta.get("columns", [])
            col_defs = ", ".join(f"{c['name']}({c['type']})" for c in cols)
            context_lines.append(f"  {schema_name}.{table}: {col_defs}")
        schema_context = "\n".join(context_lines)
    except Exception:
        table_names = []

    # Step 2: build prompt
    system_prompt = (
        f"You are a PostgreSQL expert. The database schema is '{schema_name}'. "
        f"Do NOT invent column names. All tables are in schema '{schema_name}'.\n\n"
        f"All tables belong to the '{schema_name}' schema. "
        f"Always write table names as {schema_name}.tablename (e.g. {schema_name}.customer). "
        "Return ONLY raw SQL. No explanations, no markdown, no code fences."
    )
    user_prompt = f"Question: {question}\n\nSQL (use {schema_name}.tablename.columnname exactly as listed):"

    # Step 3: call Ollama
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": f"{system_prompt}\n\n{user_prompt}",
                "stream": False
            }
        )
        resp.raise_for_status()
        raw = resp.json()
        sql = extract_sql(raw.get("response", "").strip())

    # Step 4: auto-inject schema prefix for unqualified table names
    sql = _qualify_tables(sql, schema_name, table_names)
    sql, validation_error = _validate_and_fix_sql(sql, schema_name, table_names)
    if validation_error:
        print(f"WARNING validation: {validation_error}")

    return json.dumps({"question": question, "generated_sql": sql})


def _qualify_tables(sql: str, schema_name: str, table_names: list) -> str:
    """Prefix unqualified table names, also fixing common plural/singular mismatches."""
    for table in table_names:
        variants = {table, table + "s", table.rstrip("s")}  # customer, customers, customer
        for variant in variants:
            pattern = r'(?<!\.)(?<!\w)\b' + re.escape(variant) + r'\b'
            sql = re.sub(pattern, f"{schema_name}.{table}", sql, flags=re.IGNORECASE)
    return sql