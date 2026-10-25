<p align="center"><img src="https://raw.githubusercontent.com/voodoomods/hypswarm/main/site/assets/hypswarm.svg" width="72" alt=""></p>

<h1 align="center">hypswarm</h1>
<p align="center"><b>Many agents. One record.</b><br>
Run one agent or a swarm of them on a research, engineering, trading, knowledge or optimisation task, with a
<a href="https://hypgraph.com">HypGraph</a> record as the only shared state.<br>
<a href="https://hypswarm.com">hypswarm.com</a> · <a href="https://hypswarm.com/llms.txt">for agents</a> ·
<a href="docs/DESIGN.md">the design</a> · <a href="docs/decisions/">decisions</a> · <a href="https://hypgraph.com">HypGraph</a></p>

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
`StubModel` for tests. `pip install "hypswarm[anthropic]"` adds `Anthropic("claude-sonnet-5-5")` over the
Messages API, prompt-cache reads counted. Any object with `async complete(messages, tools) -> Reply` is a model.

## Installing, today

hypswarm needs HypGraph's coordination layer, which ships with hypgraph 0.4:

```bash
pip install --pre hypswarm                 # pulls hypgraph>=0.4; --pre while it is an alpha
```

## Status

Alpha. Built from the harness the HypGraph harmony study runs agent teams on, and measured there as a
preregistered condition before anything is claimed for it. What's built: the scheduler, workers, five profiles with
rosters, the tool registry, external seats over MCP, the record server with token-bound writes, resume, escalation,
instrument reproduction, verified file tools, the OpenAI-compatible and Anthropic adapters, and a test suite that
runs every scheduler path on scripted models in seconds. Every design decision is in
[docs/decisions](docs/decisions/).

Made by Nicolas Houghtaling at [VoodooMods LLC](https://github.com/voodoomods). Apache-2.0.
