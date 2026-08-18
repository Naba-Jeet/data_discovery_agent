"""
DQ Engine — loads rules, runs checks, saves results + score.
"""
import asyncpg
import os, json
from dotenv import load_dotenv
from dq import store
from dq.checks import null_check, unique_check, freshness_check, volume_check, range_check, custom_check

load_dotenv()

SOURCE_DSN = (
    f"postgresql://{os.getenv('CLIENT_PG_USER')}:{os.getenv('CLIENT_PG_PASSWORD')}"
    f"@{os.getenv('CLIENT_PG_HOST')}:{os.getenv('CLIENT_PG_PORT')}/{os.getenv('CLIENT_PG_DB')}"
)

CHECK_MAP = {
    "null":      null_check.run,
    "unique":    unique_check.run,
    "freshness": freshness_check.run,
    "volume":    volume_check.run,
    "range":     range_check.run,
    "custom":    custom_check.run,
}


async def run_dq_checks(schema: str, table: str) -> dict:
    """Run all active DQ rules for a table. Returns report dict."""
    rules = await store.get_rules(schema, table)
    print(f"DEBUG run_dq_checks got {len(rules)} rules")

    if not rules:
        return {
            "schema": schema,
            "table": table,
            "score": None,
            "message": "No active DQ rules found for this table.",
            "results": [],
        }

    source_conn = await asyncpg.connect(SOURCE_DSN)
    results = []
    rule_ids = []

    try:
        for rule in rules:
            print(f"DEBUG rule: {rule}")
            check_fn = CHECK_MAP.get(rule["rule_type"])
            print(f"DEBUG check_fn: {check_fn}")
            if not check_fn:
                continue
            raw_params = rule["parameters"]
            print(f"DEBUG raw_params type: {type(raw_params)}, value: {raw_params}")
            if isinstance(raw_params, str):
                try:
                    params = json.loads(raw_params)
                except Exception:
                    params = {}
            elif isinstance(raw_params, dict):
                params = raw_params
            else:
                params = {}
            print(f"DEBUG params after parse: {params}")
            result = await check_fn(
                source_conn,
                schema,
                table,
                rule["column_name"],
                params,
            )
            print(f"DEBUG check result: {result}")
            result["severity"] = rule["severity"]
            result["rule_id"] = rule["id"]
            results.append(result)
            rule_ids.append(rule["id"])
    finally:
        await source_conn.close()

    # Save to data_discovery DB
    try:
        await store.save_results(schema, table, results, rule_ids)
        score = await store.save_score(schema, table, results)
    except Exception as e:
        print(f"DEBUG save error: {e}")
        score = None

    return {
        "schema": schema,
        "table": table,
        "score": score,
        "total_rules": len(results),
        "passed": sum(1 for r in results if r["status"] == "pass"),
        "failed": sum(1 for r in results if r["status"] == "fail"),
        "warned": sum(1 for r in results if r["status"] == "warn"),
        "results": results,
    }