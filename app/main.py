"""
FastAPI entry point for the data-agent app service.
Exposes a single /chat endpoint that drives the LangGraph agent.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent.orchestrator import run_agent
from agent.intent import classify, extract_table
from config import APP_HOST, APP_PORT
import uvicorn
from api.endpoints.anomaly_column import router as anomaly_column_router
from api.endpoints.anomaly_timeseries import router as anomaly_ts_router

app = FastAPI(title="Data Agent", version="0.1.0")

app.include_router(anomaly_column_router)
app.include_router(anomaly_ts_router)


class ChatRequest(BaseModel):
    message: str
    pg_schema: str = "public"
    target_table: str = ""
    target_column: str = ""
    rule_type: str = "null"
    column_name: str = ""
    parameters: str = "{}"
    severity: str = "warn"
    warehouse: str = "postgres"
    databricks_token: str = ""


class ChatResponse(BaseModel):
    intent: str
    final_response: str
    tool_result: dict = {}
    llm_response: str = ""


class RowAnomalyRequest(BaseModel):
    pg_schema:        str
    table_name:       str
    frequency:        str                    # daily|weekly|monthly|quarterly|yearly
    date_column:      str   = ""             # optional — auto-resolved if blank
    lookback_periods: int   = 0              # 0 = use frequency default
    threshold_pct:    float = 30.0
    username:         str   = "default"


class RowAnomalyResponse(BaseModel):
    meta:             dict
    anomalies_found:  int
    summary:          str
    result:           list
    session_id:       str = ""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        state = await run_agent(
            user_message=req.message,
            pg_schema=req.pg_schema,
            target_table=req.target_table,
            target_column=req.target_column,
            rule_type=req.rule_type,
            column_name=req.column_name,
            parameters=req.parameters,
            severity=req.severity,
            warehouse=req.warehouse,
            databricks_token=req.databricks_token
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return ChatResponse(
        intent=state.get("intent", "unknown"),
        final_response=state.get("final_response", ""),
        tool_result=state.get("tool_result", {}),
        llm_response=state.get("llm_response", ""),
    )

@app.post("/anomaly/row-count", response_model=RowAnomalyResponse)
async def row_count_anomaly(req: RowAnomalyRequest):
    import json
    from mcp_client.client import call_tool

    try:
        raw = await call_tool("tool_detect_row_anomaly", {
            "schema_name":      req.pg_schema,
            "table_name":       req.table_name,
            "frequency":        req.frequency,
            "date_column":      req.date_column,
            "lookback_periods": req.lookback_periods,
            "threshold_pct":    req.threshold_pct,
        })
        result = json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return RowAnomalyResponse(
        meta=result.get("meta", {}),
        anomalies_found=result.get("anomalies_found", 0),
        summary=result.get("summary", ""),
        result=result.get("result", []),
    )

if __name__ == "__main__":
    uvicorn.run("main:app", host=APP_HOST, port=APP_PORT, reload=True)