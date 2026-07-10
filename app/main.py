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

app = FastAPI(title="Data Agent", version="0.1.0")


# ── Request / Response models ─────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    pg_schema: str = "public"
    target_table: str = ""
    target_column: str = ""
    rule_type: str = "null"
    column_name: str = ""
    parameters: str = "{}"
    severity: str = "warn"


class ChatResponse(BaseModel):
    intent: str
    final_response: str
    tool_result: dict = {}
    llm_response: str = ""


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
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return ChatResponse(
        intent=state.get("intent", "unknown"),
        final_response=state.get("final_response", ""),
        tool_result=state.get("tool_result", {}),
        llm_response=state.get("llm_response", ""),
    )

if __name__ == "__main__":
    uvicorn.run("main:app", host=APP_HOST, port=APP_PORT, reload=True)