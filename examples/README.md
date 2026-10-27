# HypSwarm examples

Ten runnable examples. Every one runs **for free** on scripted models (the default) and for **cents** on a real
provider (`--model <id>` over `OPENAI_BASE_URL` / `OPENAI_API_KEY`). The scripted models answer from values the
example computed itself, through the same record tools, the same scheduler and the same refusals a real model
meets — so what you see is the record's behaviour, not a mock of it. Several examples make a deliberately wrong
first write so the trace shows the refusal and the honest rewrite.

```bash
pip install --pre hypswarm                       # 01–05, 07–10
pip install --pre "hypswarm[langgraph,pydantic-ai,crewai]"   # 06, the mixed swarm
cd examples/01-eval-report && python run.py --fresh
```

Every `run.py` takes `--fresh` (empty record), `--trace` (every tool call and reply, per order), `--quiet`,
`--budget-calls`, `--budget-usd`, `--pricing`. Afterwards: `hypgraph --db record.hypgraph serve` opens the HypGraph UI, where the **Live** view replays the run
from its telemetry. Each of 01–05 is also on [hypgraph.com/examples](https://hypgraph.com/examples/), replayed live.

| # | example | profile | what it shows | the refusal it provokes |
|---|---|---|---|---|
| 01 | [eval-report](01-eval-report/) | scientific | two workers, a critic, the instrument confirming every value, a report linted against the record | `SIGNIFICANCE_NOT_SHOWN` (with a real model) |
| 02 | [software-tests](02-software-tests/) | software | the instrument runs the tests; `tests_pass` is met by **its** run; a claim of "passes" before the re-run is refused, reworked, accepted | `PASS_WITHOUT_INSTRUMENT_RUN` |
| 03 | [paper-trading](03-paper-trading/) | trading | a backtest on a held-out window with fees and slippage; costless results and in-sample "edge" are refused | `BACKTEST_WITHOUT_COSTS`, `EDGE_WITHOUT_OOS_COSTS` |
| 04 | [sourced-brief](04-sourced-brief/) | knowledge | three facts, each a source node and a claim that cites it; a bare claim from recall is refused | `CLAIM_WITHOUT_SOURCE` |
| 05 | [optimal-with-bound](05-optimal-with-bound/) | optimization | objective, feasibility and a gap; "optimal" only with a bound that meets the objective | `OBJECTIVE_WITHOUT_FEASIBILITY`, `OPTIMAL_WITHOUT_BOUND` |
| 06 | [mixed-swarm](06-mixed-swarm/) | scientific | **LangChain, PydanticAI, CrewAI, Claude / Bedrock and a person on one record**: five frameworks, one set of rules | the same refusals, from every framework, in the same words |
| 07 | [human-reviewer](07-human-reviewer/) | scientific | you hold the reviewer seat over MCP (or `--auto` plays you from a second process) | — |
| 08 | [served-record](08-served-record/) | scientific | one `hypgraph serve` with two tokens; the swarm over HTTP; 401 / 403 shown before the run | — |
| 09 | [resume-and-notice](09-resume-and-notice/) | scientific | stop a run with an order open, resume and adopt it; withdraw a file mid-run and watch the record say so | — |
| 10 | [custom-seat-and-toolkit](10-custom-seat-and-toolkit/) | scientific | your own toolkit (`toolkits.register`) and your own seat (`Seat(agent=…)`) with no model at all | — |

## What every example has in common

- **Orders come from the record.** The scheduler reads the question board and issues work; seats are matched on
  the words they `take`. A seat never picks its own work.
- **One write for a result and its claim.** `register_run(name, result_summary, values, code, claim, answers, scope)`
  records the run, the result, and the claim whose numbers are bound to the result's values.
- **The instrument re-runs the code** before any review and files a lab run that `replicates` the author's. The
  review order says which values were confirmed, unprinted or contradicted; a reviewer recomputes only a
  contradiction.
- **Done is the record's call.** Every reply says `MET` / `NOT MET` per predicate and "return_work now" when all
  are. Reworks say what was missing; a third rework without a changed predicate is refused.
- **Budget is a rule**, counted with calls in flight, printed in every reply.

## Writing your own

Copy `10-custom-seat-and-toolkit`. The two extension points are a toolkit factory and an agent function; the
framework bridges in `06-mixed-swarm` show how a LangChain / PydanticAI / CrewAI agent becomes an agent function
in one line. `_common.py` holds the shared CLI, the host sandbox and the scripted models.
