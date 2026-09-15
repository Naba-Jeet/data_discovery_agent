# app/api/endpoints/anomaly_column.py

import pandas as pd
from fastapi import APIRouter, HTTPException
from api.schemas.anomaly_schemas import ColumnAnomalyRequest, ColumnAnomalyResponse
from ml.anomaly import detect_outliers, detect_zscore_outliers
from mcp_client.client import run_query

router = APIRouter(prefix="/anomaly", tags=["Anomaly"])


@router.post("/column", response_model=ColumnAnomalyResponse)
async def column_anomaly(request: ColumnAnomalyRequest):

    # 1. Fetch data from DB via existing MCP client
    sql = f"SELECT * FROM {request.table_name} LIMIT 10000"
    try:
        raw = await run_query(sql)
        # run_query returns a plain JSON string — a list of row dicts
        import json
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if not parsed:
            raise HTTPException(status_code=404, detail=f"No data found for {request.table_name}")
        # parsed is a list of dicts directly
        rows = parsed if isinstance(parsed, list) else parsed.get("rows", [])
        if not rows:
            raise HTTPException(status_code=404, detail=f"No data found for {request.table_name}")
        df = pd.DataFrame(rows)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB fetch failed: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=404, detail="Table returned empty result")

    isolation_results = None
    zscore_results    = None

    # 2. Run selected method(s)
    if request.method in ("isolation", "both"):
        isolation_results = detect_outliers(
            df,
            numeric_cols=request.numeric_cols,
            contamination=request.contamination,
        )

    if request.method in ("zscore", "both"):
        zscore_results = detect_zscore_outliers(
            df,
            numeric_cols=request.numeric_cols,
            threshold=request.zscore_threshold,
        )

    # 3. Summary
    summary = {
        "total_rows":          len(df),
        "columns_analyzed":    request.numeric_cols or df.select_dtypes(include="number").columns.tolist(),
        "isolation_anomalies": isolation_results.get("anomaly_count") if isolation_results else None,
        "zscore_anomalies":    sum(
            v["outlier_count"] for v in zscore_results["column_results"].values()
        ) if zscore_results and "column_results" in zscore_results else None,
    }

    explanation = None
    if request.explain:
        from ml.explain.llm_explain import explain_anomalies
        explanation = await explain_anomalies({
            "table":     request.table_name,
            "type":      f"Column Anomaly ({request.method})",
            "summary":   summary,
            "anomalies": (isolation_results or {}).get("anomalies", [])[:5],
        })

    return ColumnAnomalyResponse(
        table_name=request.table_name,
        method=request.method,
        isolation_results=isolation_results,
        zscore_results=zscore_results,
        summary=summary,
        explanation=explanation
    )