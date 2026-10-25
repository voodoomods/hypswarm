# ADR-009 — A seat may be held by an agent from another framework; the record still governs it

**Date** 2026-10-25 · **Status** accepted · **Supersedes** nothing · **Related** ADR-002 (the harness is reserved),
ADR-004 (escalation by the record), ADR-007 (reproduce, don't recompute), ADR-008 (profiles, rosters, toolkits)

## Context

Teams already have agents: LangChain / LangGraph graphs, PydanticAI agents, CrewAI crews, in-house loops. The
model-level adapters (`providers/`) let a seat use any *model*, but the seat still runs HypSwarm's own loop. A
team that wants to keep its agent — its prompts, its tools, its memory — and still get the record's governance
had no way in short of the MCP path, which is pull-based and out of process.

## Decision

1. **`Seat.agent`**: a seat may carry an *agent function* instead of a model, `async (AgentOrder) -> AgentOutcome
   | str | None`. The scheduler dispatches it like any seat; `worker.run_agent_order` gives it the same order
   text, the same system prompt and the same tools a native seat gets (the record's tools and the host's data
   tools the seat may use), plus the calls left in the run.
2. **The record still judges.** The agent's writes go through the same record tools, so the same refusals apply
   and done is still the record's call. If the agent does not call `return_work`, HypSwarm returns the order with
   the agent's note; if it raises, the order is returned by the record with the error. A reviewer seat held by an
   agent cannot write claims (ADR-005 holds).
3. **Budget by report.** One call is reserved before the agent starts (a run at its budget never starts an
   agent); the agent reports the calls and tokens it made, which the meter counts when it ends. Frameworks cannot
   be gated call by call from outside, so the bridge passes `calls_left` and caps the framework's own loop with
   it (LangGraph `recursion_limit`, PydanticAI `UsageLimits(request_limit)`, CrewAI `max_iter`).
4. **Bridges translate tools, nothing else.** `hypswarm.bridges.{langchain, pydantic_ai, crewai}` turn hypswarm
   `Tool`s into the framework's native tool shape (`StructuredTool` with a pydantic args model built from the
   tool's JSON schema and the function's own defaults; `pydantic_ai.Tool` from the typed signature;
   `crewai.tools.BaseTool` with `args_schema`), run the user's factory-built agent on the order, and read usage
   back (`usage_metadata`, `result.usage`, `crew.usage_metrics`). They add no prompting of their own beyond the
   seat's system prompt.
5. **Model adapters for the rest.** `providers.bedrock.Bedrock` (Converse API, every Bedrock model with tool use)
   and `providers.langchain.LangChainModel` (any `BaseChatModel` with `bind_tools`) cover the model-level case
   without a framework.

## Consequences

- Five frameworks on one record is a configuration, not an integration project (`examples/06-mixed-swarm`).
- The per-order call cap is enforced *after* the fact for agent seats. A runaway framework loop can overspend one
  order by what its own limit allows; the run's budget still ends the run. Documented on the engineers page.
- An agent's tool calls are visible to the scheduler only if the bridge reports them (`AgentOutcome.log`); the
  record's own writes are always visible, since they are in the record.
- CrewAI's executor expects a native tool-calling LLM to return a *list* of tool calls and runs the tools itself;
  the bridge's tools are built one closure per tool (a loop-local class shared the last function — found by the
  first test).
- Verified with scripted models for each framework (`tests/test_bridges.py`); real-provider runs are the
  examples' `--real` mode. LangGraph itself could not be imported on the development machine (an application
  control policy blocks `ormsgpack`'s DLL); the LangChain bridge test falls back to a minimal Runnable loop and
  CI runs the LangGraph path.
