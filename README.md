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

A profile is a HypGraph governance profile — what the **record** will accept and refuse, and the discipline's own
**workflow**: the stages a question passes through and the gate out of each — plus the seats and tools that usually
work under it. It is pinned on the investigation and versioned, so a record written under `trading@2` means the
same thing in a year. A name (`trading`) is its newest version; `trading@1` pins the pre-workflow one.

| profile | roster | the stages a question passes through | the record refuses |
|---|---|---|---|
| `scientific` | analyst, stats, critic, lead | asked → conjectured → preregistered → run → evidenced → claimed → reviewed | numbers no result accounts for; "never" without the count; "significant" without the test; a check on stale evidence |
| `software` | implementer, tester, reviewer, lead | specified → implemented (a diff by hash) → verified (**the instrument ran the tests on that head**) → claimed → reviewed | "it passes" without an instrument-recorded run, or on a superseded head; the diff's author as its reviewer |
| `trading` | quant, risk, lead | asked → thesised → preregistered → backtested (**out of sample, after costs, trials declared**) → claimed → risk-reviewed → positioned → monitored | a backtest without the costs it charged; "edge" without both, or without the configurations tried; a position without size, stop and review date; any live order (there is no path) |
| `knowledge` | researcher, fact_checker, lead | asked → (searched) → sourced (**the passage that says it**, retrieved, kind) → claimed → checked | a factual claim with no source; a source without its passage |
| `optimization` | modeller, solver, verifier, lead | posed (the instance by hash) → modelled → configured → solved → verified → claimed → checked | an objective without feasibility; "optimal" without a bound, or on a changed instance; a solve that uses no instance |

**The stage is derived, never set.** The record reads a question's stage off what has been written
(`hypgraph`'s `stage()`); the scheduler issues that stage's order — the gates up to the next review as its
done-when, to the seat the stage names — and a review stage goes to a reviewer on the node the previous gate
produced. A question is complete when the record says so. An honest "it can't be answered" — a checked claim of kind
`inconclusive`, derived from what the search did find — completes a question at any stage; declining a thesis is a
decision (`kind=no_position`).

Every profile adds a paragraph of its rules to each seat's preamble and tells the scheduler what "complete" means
(`completion()`); `hypswarm profiles` lists them. Adding a discipline is a `Profile` with a `Workflow` in HypGraph
plus a roster here — the scheduler does not change. The method each workflow is taken from is quoted in HypGraph's
[`docs/workflows/`](https://github.com/voodoomods/hypgraph/tree/main/docs/workflows).

### Workflows, per profile

What each stage's order asks a seat to write, and what the record refuses on the way. *Italic* steps are
mechanical — no model is called.

**scientific** — question → a hypothesis with predictions → an experiment that tests it with the expected outcome,
**before** any run → `register_run` executing it (run + result + claim, numbers bound) → *instrument re-runs the
code* → `review` by the critic (judges; recomputes only a contradiction) → *question settled* → report from the facts,
linted. A corrected data file puts what rested on it at risk; a check on stale evidence doesn't count.

**software** — requirement → the change as an artifact `kind=diff` (base → head sha, files) → `register_run` with
the exact test command as code and `uses` the diff → *instrument runs the tests on that head* (`tests_pass_current`)
→ claim "passes", accepted only now → `review` by someone who wrote neither the claim nor the diff → *requirement
verified*. A newer head supersedes the old diff: the tests go stale and the gate reopens.

**trading** — market question → the thesis as a hypothesis → the backtest preregistered as an experiment (windows,
costs, configurations to try) → `register_run` with oos_return, fees, slippage, **trials** → *instrument re-runs the
backtest* → `review` by the risk seat → a `decision` `based_on` the claim: `kind=position` with size, stop,
review_date, paper — or `kind=no_position` → *monitored*: past its review date with nothing newer, the position is
flagged.

**knowledge** — question → (the search as an experiment, optional) → `source` node (citation, URL or DOI, **the
passage**, retrieved, kind) `part_of` the question → claim that `cites` it → `review` by the fact-checker, who opens
the source → *all checked*. A withdrawn source puts every claim citing it at risk. No source? The search's own result
("read 3 of 3 pages; 0 mention it") and a claim `kind=inconclusive` derived from it settle the question honestly.

**optimization** — question + the instance as an artifact `kind=instance` → the model as a hypothesis → the solve
configuration as an experiment → `register_run` that `uses` the instance, with objective, feasible, bound or gap →
*instrument re-runs the solve* → `review` of the result by the verifier against the instance → claim "best found,
gap x", or "optimal" only with a bound → `review` of the claim → *incumbent verified*. A changed instance supersedes
the solve.

Each of these is one of the [examples](https://github.com/voodoomods/hypswarm/tree/main/examples), runnable for free;
the trace shows every stage order and the refusals on the way.

## Watching a run

Every run that writes a record file also writes `<record>.telemetry.jsonl`: each model call, tool call, work order and
scheduler decision as a span, with tokens, cost and timing. Serve the record and open the HypGraph UI's **Live** view to
watch the swarm work: which seat is calling the model or running a tool right now, what each has spent, and a trace of
where a work order's time went.

```bash
hypgraph --db desk.hypgraph serve        # then run the swarm against desk.hypgraph and open Live
hypgraph --db desk.hypgraph export --telemetry -o desk.bundle.json   # a bundle that replays the run with no server
```

See it on five finished runs, one per profile: [hypgraph.com/examples](https://hypgraph.com/examples/).

`otel=True` sends the same spans and metrics to OpenTelemetry (`pip install 'hypswarm[otel]'`). Prompts, replies and
tool arguments stay out unless `capture_content=True`.

## When the world changes

`run(..., watch=True)` keeps the record in step with the files and pages the run used, with no model call: a file
whose bytes changed supersedes its artifact, a commit is a new head of the working tree, and (with `refetch=`) a page
that no longer says what a source quotes makes the source stale. Results computed from the old state go STALE; the
instrument re-runs them on the current files; the ones that still reproduce come back on their own, and only the
answers whose evidence really moved are redone. Nobody has to tell the team that a teammate pushed a commit or the
vendor corrected a file — the record holds the hashes.

When the lead never gets a report past the record's check, the harness writes one from the record itself — the facts
and the answers the current claims give, labelled as assembled (`res.report_source == "assembled"`).

```python
res = await run(task, None, model, record="desk.hypgraph", folder="work/", reproducer=my_sandbox,
                watch=True, refetch=my_fetch)          # the change suite: studies/discovery/PLAN-CHANGE.md
```

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
