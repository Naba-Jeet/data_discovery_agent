"""
LangGraph orchestrator — defines the agent graph.

Flow:
  START
    → classify_intent
    → rag_node          (schema fetch / grounding)
    → llm_node          (Ollama call with system prompt)
    → executor_node     (MCP tool call)
    → formatter_node    (response structuring)
  END
"""
from asyncio import graph
from asyncio import graph
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from agent.intent import classify, extract_table
from agent.nodes.rag import rag_node
from agent.nodes.llm import llm_node
from agent.nodes.executor import executor_node
from agent.nodes.formatter import formatter_node
from agent.nodes.explain_node import explain_node


# ── State schema ─────────────────────────────────────────────────────────────

class AgentState(TypedDict, total=False):
    user_message: str
    pg_schema: str          # default "public"
    target_table: str       # for anomaly detection
    target_column: str      # for anomaly detection
    intent: str
    schema_context: str
    llm_response: str
    tool_result: dict
    final_response: str
    # DQ rule fields
    rule_type: str
    column_name: str
    parameters: str
    severity: str


# ── Node wrappers ─────────────────────────────────────────────────────────────

async def classify_intent(state: AgentState) -> AgentState:
    state["intent"] = classify(state.get("user_message", ""))
    return state



# ── Graph definition ──────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("classify_intent", classify_intent)
    graph.add_node("rag",             rag_node)
    graph.add_node("llm",             llm_node)
    graph.add_node("executor",        executor_node)
    graph.add_node("formatter",       formatter_node)

    graph.set_entry_point("classify_intent")
        # Add node
    graph.add_node("explain", explain_node)

    # Intents that need LLM (Ollama) vs those that go direct to executor
    NO_LLM_INTENTS = {"dq", "schema", "query", "anomaly", "anomaly", "volume_anomaly", "row_anomaly"}

    def route_after_rag(state: AgentState) -> str:
        return "executor" if state.get("intent") in NO_LLM_INTENTS else "llm"
    
    graph.add_edge("explain", "formatter")
    graph.add_edge("classify_intent", "rag")
    graph.add_conditional_edges("rag", route_after_rag, {"llm": "llm", "executor": "executor", "explain_anomaly": "explain"})
    graph.add_edge("llm",             "executor")
    graph.add_edge("executor",        "formatter")
    graph.add_edge("formatter",        END)
    

    return graph.compile()


# Singleton compiled graph
agent_graph = build_graph()


# ── Public helper ─────────────────────────────────────────────────────────────

async def run_agent(
    user_message: str,
    pg_schema: str = "public",
    target_table: str = "",
    target_column: str = "",
    rule_type: str = "null",
    column_name: str = "",
    parameters: str = "{}",
    severity: str = "warn",
) -> dict[str, Any]:
    """Run the full agent pipeline and return the final state."""

    # Auto-extract table from message if not explicitly passed
    resolved_table = target_table or extract_table(user_message)

    initial_state: AgentState = {
        "user_message": user_message,
        "intent": classify(user_message),
        "pg_schema": pg_schema,
        "target_table": resolved_table,
        "target_column": target_column,
        "rule_type": rule_type,
        "column_name": column_name,
        "parameters": parameters,
        "severity": severity,
    }
    final_state = await agent_graph.ainvoke(initial_state)
    return final_state