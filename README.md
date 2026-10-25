<p align="center"><img src="https://hypswarm.com/assets/hypswarm.svg" width="72" alt=""></p>

<h1 align="center">HypSwarm</h1>
<p align="center"><b>Many agents. One record.</b><br>
Run one agent or a swarm of them on a research, engineering, trading, knowledge or optimisation task, with a
<a href="https://hypgraph.com">HypGraph</a> record as the only shared state.<br>
<a href="https://hypswarm.com">hypswarm.com</a> · <a href="https://hypswarm.com/agents/">for agents</a> ·
<a href="https://hypswarm.com/engineers/">for engineers</a> · <a href="https://hypswarm.com/examples/">examples</a> ·
<a href="https://github.com/voodoomods/hypswarm/blob/main/docs/DESIGN.md">the design</a> · <a href="https://github.com/voodoomods/hypswarm/tree/main/docs/decisions">decisions</a> · <a href="https://hypgraph.com">HypGraph</a></p>

---

Alpha.

The record schedules the work (orders from its question board), accepts it (predicates the record checks itself),
stops what became pointless (premises that fell), re-runs what authors computed (the instrument), and writes the
report. Models are called only to do work and to judge exceptions. A solo scientist and an orchestrated swarm are
the same program with different seats — and a trading desk, a software team or a research assistant are the same
program with a different **profile**.

```python
import asyncio
from hypswarm import Task, Budget, run
from hypswarm.providers import OpenAICompatible

task = Task(title="Does A beat B",
            mission="Two models were scored on the same items (items.csv). Find out whether A beats B.",
            questions=[("Q1", "What is A's accuracy?"), ("Q2", "Is A significantly better than B?")],
            files={"items.csv": open("items.csv", "rb").read()},
            profile="scientific")                       # or software · trading · knowledge · optimization
model = OpenAICompatible("deepseek-ai/DeepSeek-V4.1-Flash", base_url="https://api.deepinfra.com/v1/openai")
result = asyncio.run(run(task, None, model, record="study.hypgraph", budget=Budget(max_calls=150, max_usd=1.0)))
print(result.report)        # the facts from the record, the lead's interpretation under them, the answers
```

`seats=None` takes the profile's roster. Or from the shell:
`hypswarm run --task task.toml --profile software --record study.hypgraph`.

## Profiles: what counts, per discipline

A profile is a HypGraph governance profile — what the **record** will accept and refuse — plus the seats and tools
that usually work under it. It is pinned on the investigation and versioned, so a record written under
`trading@1` means the same thing in a year.

| profile | roster | an order is done when… | the record refuses |
|---|---|---|---|
| `scientific` | analyst, stats, critic, lead | a checked claim answers the question | numbers no result accounts for; "never" without the count; "significant" without the test |
| `software` | implementer, tester, reviewer, lead | **the instrument ran the tests** and a claim states it | "it passes" without an instrument-recorded run |
| `trading` | quant, risk, lead | the backtest is **out of sample and after costs** | a backtest without the costs it charged; "edge" without both; any live order (there is no path) |
| `knowledge` | researcher, fact_checker, lead | the claim **cites a source node** the record holds | a factual claim with no source — recall is not a source |
| `optimization` | modeller, solver, verifier, lead | a result carries **objective, feasible, and a bound or gap** | an objective without feasibility; "optimal" without a bound |

Every profile adds a paragraph of its rules to each seat's preamble and tells the scheduler what "complete" means
(`completion()`); `hypswarm profiles` lists them. Adding a discipline is a `Profile` in HypGraph plus a roster here —
the scheduler does not change.

### Workflows, per profile

The scheduler is the same everywhere; what differs is what each order must produce before the record calls it done,
and what the record refuses on the way. *Italic* steps are mechanical — no model is called.

**scientific** — question → `register_run` (run + result + claim, numbers bound) → *instrument re-runs the code* →
`review` by the critic (judges; recomputes only a contradiction) → *question settled* → report from the facts, linted.
Refused on the way: a number no result accounts for, "never" without the count, "significant" without the test.

**software** — requirement → the implementer's change as an artifact by hash → `register_run` with the exact test
command as code → *instrument runs the tests* (a lab run that replicates the tester's: this is `tests_pass`) →
claim "passes", accepted only now → `review` of method and wording → *requirement verified*.
Refused on the way: "it passes" before the instrument has run.

**trading** — market question → hypothesis (the thesis and the move it predicts) + experiment (the backtest
preregistered: window, costs) → `register_run` with oos_return, fees, slippage, drawdown (`backtested_oos`) →
*instrument re-runs the backtest* → `review` by the risk seat → a `decision` node: paper position, size, stop,
review date, `based_on` the claim → *position recorded*. Refused on the way: a backtest without the costs it
charged, "edge" from the fitting window, any live order (there is no path).

**knowledge** — question → read through an allowlisted fetch tool → `source` node (citation, URL or DOI, passage,
date) → claim that `cites` it (`sourced`; the passage accounts for its numbers) → `review` by the fact-checker,
who opens the source → report linted so no sentence treats an unreviewed claim as settled → *all sourced*.
Refused on the way: a claim from recall.

**optimization** — question (objective, constraints) → hypothesis (modelling choice) + experiment (solve
configuration) → `register_run` with objective, feasible, bound or gap, runtime (`feasible_bounded`) → *instrument
re-runs the solve* → `review` by the verifier against the constraints → claim "best found, gap x", or "optimal" only
with a bound that meets the objective → *incumbent feasible*. Refused on the way: an objective with no
feasibility, "optimal" without a bound.

Each of these is one of the [examples](https://github.com/voodoomods/hypswarm/tree/main/examples), runnable for free.

## What you get

- **A scheduler that makes no model calls.** It issues orders to idle seats from the question board, settles every
  returned order whose predicates are met, reworks the rest twice, cancels what a fallen premise made moot, and
  brings in the lead seat only at exceptions and for the report.
- **Workers that hold no state.** A worker's context is its order and its own turns; every reply from the record
  tells it whether its order is done. It can be killed: the lease expires and another takes the order, and a run
  that died can be **resumed** from the record (`run(..., resume=inv)`).
- **The instrument reproduces; reviewers judge.** `register_run(code=…)` keeps the code; before any review the
  host's sandbox re-runs it and the record files a lab run — values *confirmed*, *not printed*, or
  *contradicted*. A reviewer recomputes only a contradiction.
- **Claims that can't be flattered.** Every claim is checked as it is written (HypGraph's refusal rules and the
  profile's), the record binds the numbers it already holds, one review settles a question, and the final report
  is linted against the record before it is accepted.
- **A budget that is a rule.** Calls and dollars, per run and per order, counted *including calls in flight*, and
  shown to every seat.
- **Escalation the record decides.** A seat may name a deeper model (`escalate_to`); it is used from the first
  time the record sends that seat's work back NOT MET — never on the model's own say-so.
- **Files the record vouches for.** `file_tools` reads a file only when its bytes match a live artifact; a withdrawn
  file is refused with the record's reason.
- **An audit trail you didn't write.** Orders are task nodes, acceptance is a decision, the run files its own
  provenance: the record *is* the log, and it verifies by hash.

## Seats

| seat | does | model |
|---|---|---|
| `worker` | takes orders; writes runs, results, claims; returns | yes |
| `reviewer` | takes review orders; its verdicts count (named in the record's policy); it writes no claims | yes |
| `lead` | judges exceptions; writes the interpretation under the facts | yes, a deeper one |
| instrument | re-runs registered code; files lab-recorded runs | no |
| operator | a person, reached through the record | no |
| *any seat* | may be held by **an agent from another framework** (`Seat(agent=…)`): it runs its own loop on its own model; the record still judges it | its own |

Three roles, because they are what the scheduler can *check*. Jobs are seats: a name, the words it `takes`, the
toolkits it may use, a model and optionally a deeper one to escalate to.

## Tools

Tools are named bundles from a registry. hypswarm ships `files`; anything that executes code or reaches a network
is the host's to register, so the swarm never runs what the host did not choose — and a profile that asks for a
bundle the host hasn't registered fails loudly rather than running without it.

```python
from hypswarm import toolkits
toolkits.register("python", lambda ctx: [Tool.from_function(my_sandboxed_python)])
result = await run(task, None, model, record="r.hypgraph", folder="work/", toolkits=["files", "python"])
```

## People and other agents as seats

A seat can be **external**: no model behind it, just a name in the record. The scheduler issues it orders like
any other seat and waits; whoever holds that name works the order through the HypGraph MCP server and returns it:

```toml
[[seats]]
name = "nicolas"
role = "worker"
external = true
```

```bash
hypgraph --db study.hypgraph --as nicolas mcp     # in Claude Code, Cursor, or any MCP client
# my_work → the order; register_run / add / review → the writes; return_work when the reply says every predicate is met
```

The record can't tell a person from an agent except by name, and it holds them to the same rules.

## Bring your own agent

A seat can be held, in-process, by a whole agent from another framework — your prompts, your tools, your loop —
and still be governed by the record: same orders, same refusals, same instrument re-run, same budget.

```python
from hypswarm.bridges.langchain import langchain_agent          # LangChain / LangGraph: any Runnable over {"messages"}
from hypswarm.bridges.pydantic_ai import pydantic_ai_agent       # PydanticAI Agent
from hypswarm.bridges.crewai import crewai_agent                 # CrewAI Crew

seats = [Seat("analyst", "worker", agent=langchain_agent(lambda tools: create_react_agent(llm, tools))),
         Seat("stats", "worker", agent=pydantic_ai_agent(lambda tools: Agent("openai:gpt-4.1-mini", tools=tools))),
         Seat("critic", "reviewer", agent=crewai_agent(lambda tools, order: Crew(...))),
         Seat("lead", "lead")]                                   # a model, e.g. Anthropic(...) or Bedrock(...)
```

A bridge hands the agent the order, the seat's system prompt and the record's tools in the framework's own tool
shape, caps the framework's loop at the calls left in the run, and reports what it used. If the agent doesn't
call `return_work` itself, HypSwarm returns the order with its final answer as the note. Your own framework is one
`async def agent(order: AgentOrder) -> AgentOutcome` away (ADR-009; `examples/10-custom-seat-and-toolkit`).
`examples/06-mixed-swarm` runs LangChain, PydanticAI, CrewAI, Claude / Bedrock and a person on one record.

## One record server, many workers

Workers don't have to share a process. Serve the record, bind writes to tokens, and point the run at it:

```bash
hypgraph --db study.hypgraph serve --writable --no-browser --token "$SWARM_TOKEN=harness,quant,risk,lead" --token "$NIC_TOKEN=nicolas"
hypswarm run --task task.toml --profile trading --record-url http://127.0.0.1:8765
```

In Python, `run(..., record=HttpRecord(url, token=...))`. A token is bound to the authors it may write as; the
harness name is reserved, so an outside seat can hold its own name and nothing else. Every write still goes
through the record's checks, the file still verifies by hash, and workers on other processes or machines are
stateless.

## Providers

The core ships `OpenAICompatible` (DeepInfra, OpenAI, NVIDIA NIM, vLLM, Ollama, most gateways) and a scripted
`StubModel` for tests. Extras:

| extra | adapter | covers |
|---|---|---|
| `[anthropic]` | `Anthropic("claude-sonnet-5-5")` | the Messages API, prompt-cache reads counted |
| `[bedrock]` | `Bedrock("anthropic.claude-sonnet-4-5-…", region="us-east-1")` | every model Bedrock serves with tool use, through the Converse API; AWS credentials from the usual chain |
| `[langchain]` | `LangChainModel(chat_model)` | any `BaseChatModel` with `bind_tools` — ChatOpenAI, ChatAnthropic, ChatBedrockConverse, ChatOllama, … |
| `[langgraph]` `[pydantic-ai]` `[crewai]` | the bridges above | a whole agent as a seat |

Any object with `async complete(messages, tools) -> Reply` is a model.

## Examples

Ten runnable examples in [examples/](https://github.com/voodoomods/hypswarm/tree/main/examples), each free on scripted models and cents on a real provider: one per
profile (an eval report, tests the instrument runs, a paper trading desk, a sourced brief, a solve with a bound),
the mixed swarm (LangChain + PydanticAI + CrewAI + Claude / Bedrock + a person), a person as reviewer over MCP, a
served record with tokens, stop-and-resume with a file withdrawn mid-run, and a custom seat and toolkit from
scratch. Several make a deliberately wrong first write so the trace shows the refusal and the honest rewrite.

## Installing, today

HypSwarm needs HypGraph's coordination layer, which ships with hypgraph 0.4:

```bash
pip install --pre hypswarm                 # pulls hypgraph>=0.4; --pre while it is an alpha
```

## Status

Alpha. Built from the harness the HypGraph harmony study runs agent teams on, and measured there as a
preregistered condition before anything is claimed for it. What's built: the scheduler, workers, five profiles with
rosters, the tool registry, external seats over MCP, the record server with token-bound writes, resume, escalation,
instrument reproduction, verified file tools, the OpenAI-compatible, Anthropic, Bedrock and LangChain adapters,
agent seats with bridges for LangChain / LangGraph, PydanticAI and CrewAI, ten runnable examples, and a test suite
that runs every scheduler path — and every bridge — on scripted models in seconds. Every design decision is in
[docs/decisions](https://github.com/voodoomods/hypswarm/tree/main/docs/decisions).

Made by Nicolas Houghtaling at [VoodooMods LLC](https://github.com/voodoomods). Apache-2.0.
