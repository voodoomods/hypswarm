"""
06 · The mixed swarm — LangChain, PydanticAI, CrewAI, Claude and Bedrock on one record.

Five frameworks hold five seats. None of them knows about the others; none of them coordinates with the others.
They share one record: the scheduler issues each an order, the record refuses the same overclaims from each of
them in the same words, the instrument re-runs whatever they register, and a person can take a seat over MCP.

  analyst   LangChain / LangGraph agent          (bridges.langchain)   — answers Q1 from the file
  stats     PydanticAI agent                      (bridges.pydantic_ai) — answers Q2
  critic    CrewAI crew, one agent, one task      (bridges.crewai)      — reviews both claims
  lead      Claude over the Anthropic API, or any model over Amazon Bedrock, or an OpenAI-compatible model
  nicolas   (optional, --human) you, over MCP: hypgraph --db record.hypgraph --as nicolas mcp

    python run.py                 # every framework on a scripted model: free, offline, deterministic
    python run.py --real --model deepseek-ai/DeepSeek-V4.1-Flash     # the frameworks on a real OpenAI-compatible model
        env: OPENAI_BASE_URL, OPENAI_API_KEY; optional ANTHROPIC_API_KEY (lead on Claude) or AWS_REGION + BEDROCK_MODEL (lead on Bedrock)
    python run.py --human nicolas # adds you as an external reviewer seat; the run waits for your review

Needs: pip install "hypswarm[langgraph,pydantic-ai,crewai]"  (and [anthropic] / [bedrock] for the lead options).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import budget, cli, main, pricing, register_python, reproducer, show, stage

from hypswarm import Seat, Task, run
from hypswarm.providers.stub import StubModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scripted

HERE = Path(__file__).resolve().parent
ITEMS = ("item,a,b\n" + "\n".join(f"{i},{int(i % 10 != 3)},{int(i % 10 not in (3, 7))}" for i in range(1, 1001)) + "\n").encode()
KA, KB, N = 900, 800, 1000           # what the file holds, by construction
TASK = Task(title="Does A beat B (mixed swarm)", profile="scientific",
            mission="Two models were scored on the same 1,000 items (items.csv: item,a,b with 1 = right). Find out whether A beats B. "
                    "Use python on the file for every number.",
            questions=[("Q1", "What is A's accuracy?"), ("Q2", "Is A significantly more accurate than B (two-sided, 0.05)?")],
            files={"items.csv": ITEMS})


def lead_model(args):
    """The lead's model: Claude if ANTHROPIC_API_KEY is set, else Bedrock if BEDROCK_MODEL is set, else the --model."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        from hypswarm.providers.anthropic import Anthropic
        return Anthropic(os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"))
    if os.environ.get("BEDROCK_MODEL"):
        from hypswarm.providers.bedrock import Bedrock
        return Bedrock(os.environ["BEDROCK_MODEL"], region=os.environ.get("AWS_REGION", ""))
    from hypswarm.providers import OpenAICompatible
    return OpenAICompatible(args.model)


def real_bridges(args):
    """The three framework agents on a real OpenAI-compatible model (the one --model names)."""
    from hypswarm.bridges.crewai import crewai_agent
    from hypswarm.bridges.langchain import langchain_agent
    from hypswarm.bridges.pydantic_ai import pydantic_ai_agent
    base, key, model = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"), os.environ["OPENAI_API_KEY"], args.model

    def lc_factory(tools):
        from langchain_openai import ChatOpenAI
        try:
            from langgraph.prebuilt import create_react_agent
            return create_react_agent(ChatOpenAI(model=model, base_url=base, api_key=key), tools)
        except ImportError:
            return scripted.minimal_runnable(ChatOpenAI(model=model, base_url=base, api_key=key), tools)

    def pai_factory(tools):
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        return Agent(OpenAIChatModel(model, provider=OpenAIProvider(base_url=base, api_key=key)), tools=tools)

    def crew_factory(tools, order):
        from crewai import LLM, Agent, Crew
        from crewai import Task as CrewTask
        a = Agent(role="Critic", goal="Review the claim the order names against its code and values; record a verdict.",
                  backstory=order.system[:1200], tools=tools, llm=LLM(model=f"openai/{model}", base_url=base, api_key=key),
                  verbose=False, max_iter=8)
        return Crew(agents=[a], tasks=[CrewTask(description=order.text, expected_output="A note of at most 120 words.", agent=a)], verbose=False)
    return langchain_agent(lc_factory), pydantic_ai_agent(pai_factory), crewai_agent(crew_factory)


if __name__ == "__main__":
    args = cli("06 · the mixed swarm", HERE, real={"action": "store_true", "help": "the frameworks on a real model (--model)"},
               human={"default": "", "help": "add a person as an external reviewer seat with this name"})
    work = stage(HERE, {"items.csv": ITEMS})
    register_python(work)
    if args.real:
        if not args.model:
            sys.exit("--real needs --model <openai-compatible model id>")
        lc, pai, crew = real_bridges(args)
        lead = lead_model(args)
    else:
        lc, pai, crew = scripted.bridges(KA, KB, N)
        lead = StubModel(scripted.lead_script(KA, KB, N), "scripted-lead")
    seats = [Seat("analyst", "worker", takes=("accuracy", "count"), agent=lc),
             Seat("stats", "worker", takes=("significantly", "test"), agent=pai),
             Seat("critic", "reviewer", agent=crew),
             Seat("lead", "lead")]
    if args.human:
        seats.insert(3, Seat(args.human, "reviewer", external=True))
        print(f"\nYou hold a reviewer seat. In another terminal:\n  hypgraph --db {args.record} --as {args.human} mcp\n"
              "then call my_work, review the claim it names, and return_work.\n")
    res = main(run(TASK, seats, {"lead": lead}, record=args.record, budget=budget(args), pricing=pricing(args),
                   folder=work, toolkits=["files", "python"], reproducer=reproducer(work),
                   external_timeout_s=1800 if args.human else None))
    show(res, quiet=args.quiet, trace=args.trace)
    print("\nseats and what held them:")
    for st in seats:
        held = ("external (MCP)" if st.external else f"agent:{getattr(st.agent, '__name__', '')}" if st.agent is not None
                else getattr(lead, "name", "model"))
        print(f"  {st.name:9} {st.role:9} {held}")
