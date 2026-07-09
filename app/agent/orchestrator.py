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
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from agent.intent import classify, extract_table
from agent.nodes.rag import rag_node
from agent.nodes.llm import llm_node
from agent.nodes.executor import executor_node
from agent.nodes.formatter import formatter_node


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

    graph.add_edge("classify_intent", "rag")
    graph.add_edge("rag",             "llm")
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
) -> dict[str, Any]:
    """Run the full agent pipeline and return the final state."""

    # Auto-extract table from message if not explicitly passed
    resolved_table = target_table or extract_table(user_message)

    initial_state: AgentState = {
        "user_message": user_message,
        "intent": classify(user_message),   # ← was req.message (wrong)
        "pg_schema": pg_schema,
        "target_table": resolved_table,     # ← deduplicated, auto-extracted
        "target_column": target_column,
    }
    final_state = await agent_graph.ainvoke(initial_state)
    return final_state
