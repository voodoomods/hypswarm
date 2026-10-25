# hypswarm

**Run one agent or a swarm of them on a task, with a [HypGraph](https://hypgraph.com) record as the only shared
state.** Alpha.

The record schedules the work (orders from its question board), accepts it (predicates the record checks),
stops what became pointless (premises that fell) and writes the report. Models are called only to do work and
to judge exceptions. A solo scientist and an orchestrated swarm are the same program with different seats.

```python
import asyncio
from hypswarm import Task, Seat, Budget, run
from hypswarm.providers import OpenAICompatible

task = Task(title="Does A beat B",
            mission="Two models were scored on the same items (items.csv). Find out whether A beats B.",
            questions=[("Q1", "What is A's accuracy?"), ("Q2", "Is A significantly better than B?")],
            files={"items.csv": open("items.csv", "rb").read()})
seats = [Seat("analyst", "worker", takes=("accuracy", "counts")),
         Seat("stats", "worker", takes=("significant", "test")),
         Seat("critic", "reviewer"),
         Seat("lead", "lead")]
model = OpenAICompatible("deepseek-ai/DeepSeek-V4.1-Flash", base_url="https://api.deepinfra.com/v1/openai")
result = asyncio.run(run(task, seats, model, record="study.hypgraph", budget=Budget(max_calls=150, max_usd=1.0)))
print(result.report)        # the facts from the record, the lead's interpretation under them, the answers
```

Or from the shell: `hypswarm run --task task.toml --seats seats.toml --record study.hypgraph`.

## What you get

- **A scheduler that makes no model calls.** It issues orders to idle seats from the question board, settles
  every returned order whose predicates are met, reworks the rest twice, cancels what a fallen premise made
  moot, and brings in the lead seat only at exceptions and for the report.
- **Workers that hold no state.** A worker's context is its order and its own turns. The record tells it, in
  every reply, whether its order is done. It can be killed; the lease expires and another takes the order.
- **Claims that can't be flattered.** Every claim is checked as it is written (HypGraph's refusal rules), the
  record binds the numbers it already holds, one review settles a question, and the final report is linted
  against the record before it is accepted.
- **A budget that is a rule.** Calls and dollars, per run and per order, enforced by the scheduler and shown to
  every seat.
- **An audit trail you didn't write.** Orders are task nodes, acceptance is a decision, the run files its own
  provenance: the record *is* the log, and it verifies by hash.

## Seats

| seat | does | model |
|---|---|---|
| `worker` | takes orders; writes runs, results, claims; returns | yes |
| `reviewer` | takes review orders; its verdicts count (named in the record's policy) | yes |
| `lead` | judges exceptions; writes the interpretation under the facts | yes, a deeper one |
| instrument | a job runner (CI, a lab) filing lab-recorded runs | no |
| operator | a person, reached through the record | no |

## Providers

The core ships `OpenAICompatible` (DeepInfra, OpenAI, NVIDIA NIM, vLLM, Ollama, most gateways) and a scripted
`StubModel` for tests. Any object with `async complete(messages, tools) -> Reply` is a model. Anthropic and
LangChain adapters are planned as extras.

## Status

Alpha. Built from the harness the HypGraph harmony study ran agent teams on; its first measured use is as a
condition in that study. The record server mode (workers over HTTP / MCP), external MCP workers, and the
building-task adapter (CI as the instrument) are the next steps — see [docs/DESIGN.md](docs/DESIGN.md).

Made by Nicolas Houghtaling at [VoodooMods LLC](https://github.com/voodoomods). Apache-2.0.
