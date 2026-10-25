"""
Bridges: a seat held by an agent from another framework. Each bridge takes a factory that builds the framework's
agent from the record's tools in that framework's own tool shape, runs it on the order, and reports the calls and
tokens it used so the run's budget stays honest. The record judges done, refuses overclaims and keeps the
provenance exactly as for a native seat — the framework only reasons.

    from hypswarm.bridges.langchain import langchain_agent        # LangChain / LangGraph (any Runnable)
    from hypswarm.bridges.pydantic_ai import pydantic_ai_agent     # PydanticAI Agent
    from hypswarm.bridges.crewai import crewai_agent               # CrewAI Agent in a one-task Crew

Every bridge is ``AgentFn``-shaped (see ``hypswarm.agents``), so your own framework is one function away.
"""

from ..agents import AgentFn, AgentOrder, AgentOutcome

__all__ = ["AgentFn", "AgentOrder", "AgentOutcome"]
