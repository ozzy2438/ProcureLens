"""LangGraph Bid Intelligence Agent.

Single agent, four tools, strong guardrails:

    user query
      -> PII redaction (guardrails.redact)
      -> planner LLM decides tool calls
         - sql_tool: NL -> SQL over dbt marts (read-only role)
         - rag_tool: CPR / ANAO corpus retrieval with citations
         - ml_tool: amendment-risk + fit-score via model service
         - brief_tool: compose bid/no-bid brief (marked draft, human review)
      -> every step appended to audit log (agent/audit.py)
      -> final answer with source citations

Design choices (see docs/adr/0001-stack-choices.md):
- one agent + good tools > multi-agent orchestration for this scope
- RAG + tool-use, no fine-tuning
"""
from __future__ import annotations

from typing import Any


def build_graph() -> Any:
    """Compile and return the LangGraph state graph."""
    # Lazy imports keep the core package importable without agent extras.
    # TODO(week-4):
    # from langgraph.graph import StateGraph
    # from langgraph.prebuilt import ToolNode
    # ... assemble planner -> tools -> responder with audit hooks
    raise NotImplementedError
