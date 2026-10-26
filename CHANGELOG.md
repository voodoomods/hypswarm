# Changelog

## 0.1.0a4 — 2026-10-26: orders from stages

- **The scheduler issues each question's stage order.** Under a profile with a workflow (hypgraph ≥ 0.5.1's `@2`
  profiles, now what a profile name means), it asks the record which stage every question is in and issues that
  stage's order: the gates up to the next review as the done-when, to the seat the stage names (`quant`,
  `fact_checker`, …); a review stage goes to a reviewer, on the node the previous gate produced. The order text
  names the stage (`Q1 is at stage 'conjectured' (2/8) of the scientific@2 workflow — …`). A question is complete
  when the record says so; a checked `inconclusive` answer completes it at any stage, and the open order on it is
  cancelled as moot. `scientific@1` … keep the board path exactly as it was.
- Workers get `graph_link` and `register_run(uses=[…])`, so a run can name the diff it tested or the instance it
  solved; the instrument's re-run copies the author's `uses`, so `tests_pass_current` reads off the lab run.
- `HttpRecord` speaks `stages`, `stage`, `completion` and `link`.
- The examples' scripted models walk the stages their order names (hypothesis, preregistered experiment, typed
  artifact, position or no-position decision, inconclusive answer); examples 01–05 run their `@2` workflow, 06–10
  pin `scientific@1` (they are about bridges, people, served records, resume, custom seats). The discovery study's
  stub run settles every family through its stages.
- Depends on hypgraph ≥ 0.5.1.

## 0.1.0a3 — 2026-10-25

- Package metadata brought in line with HypGraph's: a one-line description, classifiers, keywords, project URLs
  (documentation, changelog), a NOTICE file. The README's links are absolute so PyPI renders them; the logo is
  served from hypswarm.com.
- CI pins `crewai>=1.15` (older executors take only text back from a custom LLM), runs every test with a timeout
  that dumps all threads' stacks, cancels a superseded run, and applies the CrewAI / OpenTelemetry opt-outs to the
  whole job. Example 08 passes its server tokens as `--token=VALUE`.
- Agent seats tolerate tool arguments reported as text (PydanticAI reports them as JSON text).
- Depends on hypgraph ≥ 0.4.2 (a question is not an assertion in the report check).

## 0.1.0a2 — 2026-10-25

- **Bring your own agent.** `Seat(agent=…)` hands a seat to a whole agent from another framework, in-process; the
  record still issues the order, judges done, refuses overclaims and re-runs the code (ADR-009).
- Bridges for **LangChain / LangGraph**, **PydanticAI** and **CrewAI**: the record's tools in each framework's native
  tool shape, the framework's loop capped at the calls left in the run, usage reported back.
- Model adapters for **Amazon Bedrock** (Converse API) and any **LangChain** chat model.
- `examples/`: ten runnable examples, free on scripted models — one per profile, the mixed swarm, a person as
  reviewer over MCP, a served record with tokens, stop-and-resume with a file withdrawn mid-run, a custom seat and
  toolkit. CI runs all ten.
- Reproduction verdicts ignore a sandbox's stderr and treat a traceback as a failed re-run; a host's `stop()` ends
  the run as `stopped`.
- Site: the HypSwarm brand, the hero's living graph, a Workflows section per profile, `/examples/`.

## 0.1.0a1 — 2026-10-25

- First alpha on PyPI, on hypgraph 0.4: the scheduler, stateless workers, five governance profiles with rosters
  (`scientific`, `software`, `trading`, `knowledge`, `optimization`), the tool registry, external seats over MCP,
  the record server with token-bound writes, resume from the record, escalation by the record's NOT MET,
  instrument reproduction, verified file tools, the OpenAI-compatible and Anthropic adapters, and a test suite
  that runs every scheduler path on scripted models in seconds. Decisions in `docs/decisions/`.

## 0.0.1 — 2026-10-24

- A dependency-free placeholder that reserved the name on PyPI and pointed at the alpha on GitHub.
