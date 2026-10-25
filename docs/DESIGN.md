# hypswarm — design, alpha

*Draft 1, 2026-10-24. Not built yet. Written after four harmony pilots (37 runs of agent teams coordinating
through a HypGraph record), whose logs are the evidence for most choices below.*

**One sentence.** hypswarm runs one agent or a swarm of them on a research or building task, with a HypGraph
record as the only shared state: the record schedules the work, accepts it, stops what became pointless, and
writes the report; models are called only to do work and to judge exceptions.

---

## 1. What the pilots taught, and what it forces

| Observed | Consequence for the design |
|---|---|
| Most of what an orchestrator model did was mechanical: what is open, who is on what, is this done, accept it. In pilot 3 those were 25–40 % of its calls. | The scheduler is code, not a model. A model is called only for judgement. |
| Sub-agents worked past done until the record told them they were done; they returned when it did. | Every tool reply carries the agent's control state. No agent asks whether it is finished. |
| An order's predicate could be unmeetable with the agent's tools; the lead reworked it three times. | Orders are meetable by construction (D-10): the record decides done-ness from what was written under the lease. |
| Two workers re-derived the same numbers in one run; the record's lease stopped a third. | Parallel workers are safe only because the record leases targets. Parallelism is a scheduler feature, not a prompt instruction. |
| The best reports came from the record condition: every number traceable, the trap named. | The report is generated from the record; the model writes interpretation under it and the linter gates it. |
| A whole run cost cents; the cost was retries and turns, never the checks. | The budget is enforced by the scheduler in calls and dollars, per run and per order, and shown in every reply. |

## 2. Build or borrow

**Decision: a thin harness of our own over an OpenAI-compatible chat adapter, with LangChain and Anthropic as
optional adapters, and MCP as the worker protocol.** Reasons:

- The control loop *is* the record. LangGraph and deepagents exist to hold agent state in a graph of their own,
  checkpoint it and route between nodes; here the record is the state and the checkpoint, and routing is the
  scheduler. Building on them means two state machines that disagree. Pegasus runs on deepagents and pays for
  that in middleware stacks and 35,000-token calls.
- The study runner (`Pegasus/pod/dev/study_runner.py`, condition C) is already a working embryo in ~200 lines
  of its own loop plus `langchain_core`'s message and tool types. Nothing in it needs LangChain's agent
  machinery. The model-facing surface is four tool shapes and one call: `model(messages, tools) -> message`.
- An OpenAI-compatible adapter covers DeepInfra, OpenAI, NVIDIA NIM, vLLM, Ollama, Together and most gateways
  with one `httpx` client. Anthropic gets its own adapter. A `langchain` adapter wraps any `BaseChatModel` so
  LangChain users bring their models without us depending on LangChain.
- **MCP is the worker protocol.** The HypGraph MCP server already exposes `my_work`, the record tools and
  `return_work`. A worker is anything that can hold an MCP session and act on a work order: hypswarm's built-in
  worker, a human developer's Claude Code or Cursor session, or a third-party agent. That is how "usable by
  humans and agents" is met without two code paths: a person and an agent take the same order from the same
  board, and the record can't tell them apart except by name.

Dependencies of the core: `hypgraph`, `httpx`. Extras: `[anthropic]`, `[langchain]`, `[mcp]` (FastMCP client,
to drive external workers), `[server]`. Python ≥ 3.10. Stdlib `dataclasses` for config; no pydantic in the core.

## 3. The agent

There is one program. "Solo scientist" and "orchestrator with a swarm" are the same program with different
seats and a worker count.

### 3.1 Seats, not personalities

A seat is a declared capability bound to one author name in the record. Prompts stay short; the work order
carries the task.

| Seat | What it does | Model? |
|---|---|---|
| **worker** | Takes orders from the board; writes runs, results, claims; returns. Declares `takes` (kinds of work) and `tools` (data tools it may use). | yes |
| **reviewer** | Takes review orders. Named in the record's `Policy.reviewers`, so its verdicts count. Never reviews its own author's work (the record refuses). | yes |
| **lead** | Called at exceptions only: an order NOT MET after two reworks, a contested claim, an empty frontier with unsettled questions, and the report's interpretation. | yes, deeper model |
| **instrument** | Not a model. A job runner (CI, a lab) that files runs as the policy's `instrument`, so its results are lab-recorded rather than agent-reported. | no |
| **operator** | A person. Approves budgets, answers escalations, resolves objections. Reached through the record (a question node + a notification), never through chat state. | no |

A solo scientist is one worker seat that is also a reviewer of nobody (its claims stay unchecked, honestly) plus a
lead that is the same model; the scheduler still issues it orders from the board, one at a time. A swarm is *k*
workers and *r* reviewers pulling in parallel.

### 3.2 The worker loop

```
order = my_work()                          # the record's text: objective, target, premises, known, predicates with recipes
loop (≤ turn cap, ≤ order budget):
    reply = model(system=seat prompt, messages=[order, …], tools=data tools + record tools)
    run its tool calls; every record write returns the order's predicate status
    stop when the model calls return_work, or the reply says every predicate is met and the model stops calling tools
```

The worker holds no state between orders. It can be killed and another worker takes the lease when it expires.
Its context is the order text plus its own turn history, nothing else; the record is read on demand with `show`.

### 3.3 The scheduler (no model calls)

```
until every question is settled, or the budget is spent, or the operator stops it:
    board = question_board()
    cancel_moot()                                               # premises that fell
    settle()                                                    # returned orders with every predicate met
    for order in returned and not met:
        rework ≤ 2 (what is missing, from check_work)           # then escalate to the lead seat
    for question in board where open, no order, a worker is idle:
        issue_work(question → best-fit worker by takes; default predicates)
    for question where answered and unchecked, a reviewer is idle:
        issue_work(answering claim → reviewer, [reviewed])      # one review settles a question
    for experiment on the frontier (planned, unleased), a worker is idle:
        issue_work(experiment → worker)
    wait for a return (asyncio), or a lease to expire
report: order the lead to write the interpretation under report(); submit only when check_text passes
```

Best-fit is deterministic (a worker's `takes` against the target's type and the question's words, idle first),
like Pegasus's dispatcher. Every scheduler action is already an event in the record (orders are task nodes;
acceptance is a decision), so the run's audit trail is the record itself.

### 3.4 Many angles, one record

A swarm attacks a problem from several angles by construction: the lead (or the task author) adds rival
hypotheses with `alternative_to` and experiments that `tests` them with stated expectations; `next_experiments`
ranks by how well they separate the hypotheses; workers take different experiments under leases; results that
share a run or data count as one line of support; a claim built on a withdrawn premise goes AT RISK and the
orders resting on it are cancelled. None of that is new code; it is what the record already derives. hypswarm's
job is to keep workers pulling from it.

### 3.5 Building tasks

Same program, one convention: the CI runner is the `instrument`. A requirement is a question. A design choice is
a decision `based_on` the claims that justify it, flagged REVISIT when one falls. A change is a run (`code`
artifact = the commit sha) that produced a result (tests passed of tests run), filed by CI as lab-recorded.
"The change makes the tests pass" is a claim with a k/n measurement bound to that result, so the agent can't
assert it; only the instrument can produce the number. A regression is a withdrawal with a blast radius. No new
node types.

## 4. Enterprise grade, concretely

- **One record server, many stateless workers.** `hypgraph serve --writable` (or the MCP server over HTTP) is
  the single writer; workers talk to it over MCP/HTTP with a bearer per seat, never to the SQLite file. Workers
  scale horizontally and die safely; the record is the checkpoint and the audit log.
- **Budget as a hard rule.** Per run and per order, in calls and dollars; the scheduler refuses to issue an
  order that can't fit; the worker sees calls remaining in every reply. Spend is read from the host's meter when
  one exists (Pegasus's proxy ledger), else counted from the provider's usage fields.
- **Provenance of the run itself.** Every run files one `run` node of kind `agent` holding: hypswarm version,
  record version, the seats and their models, prompt hashes, tool versions, seeds, start/finish. A run is
  reproducible from the record and the seeds.
- **Secrets never in the record.** API keys live in the adapters' environment; the record holds author names and
  hashes. Tool outputs are scrubbed before they are written as notes (the Pegasus scrubber, ported).
- **Resumable, idempotent.** A restarted run reads the board and continues; orders carry leases with expiry;
  nothing is re-issued that is open, nothing re-done that is settled.
- **Observable.** Structured logs (one JSON line per scheduler action and model call, with the order code),
  optional OpenTelemetry spans, and `hypswarm status` reading the board. The Atlas gets an *Orders* card.
- **Typed, tested, versioned.** A typed public API (`hypswarm.run(task, seats, record, budget)`), `py.typed`,
  mypy-clean, a test suite that runs every scheduler path on a stub model in seconds, the same preregistered
  task suite as the harmony study for end-to-end checks, semantic versioning, Apache-2.0.
- **A CLI people can operate.** `hypswarm run --record study.hypgraph --task task.md --seats seats.toml
  --budget 2.00`, `hypswarm status`, `hypswarm stop`, `hypswarm resume`, `hypswarm report`.

## 5. Measuring it

hypswarm joins the harmony study as **condition E, "record-scheduled swarm"**: four workers in parallel, one
reviewer, a lead called only at exceptions, same task suite, same caps, same subject model, preregistered as a
deviation before it runs. Against C it isolates two things: how much of the lead's cost the scheduler removes
(calls per run, lead calls per run), and what parallelism does to wall time at the same spend. Against B it is
the comparison that matters for the paper. The study already meters every call and labels every unit, so no new
instrumentation is needed. Prediction, stated now: calls per run near D's (≈ 80), lead calls under 10, wall time
cut by roughly the worker count on families with independent sub-questions, and no change on F7's cascade,
which is sequential by nature.

## 6. Build order (alpha)

1. **Scaffold** (`src/hypswarm/`): `seats.py`, `providers/` (openai_compat, anthropic, langchain), `worker.py`,
   `scheduler.py`, `budget.py`, `run.py` (the public API), `cli.py`; tests on a stub provider.
2. **Port condition C** from the study runner into it, then make the study harness run condition E through
   hypswarm. Measure (§5).
3. **MCP workers**: external agents join a run by holding an MCP session; the scheduler sees them as seats.
4. **Operator surface**: `hypswarm status`, the Atlas Orders card, operator questions through the record.
5. **Building adapter**: CI as instrument, the commit-as-artifact convention, one worked example repo.

Step 2 is the one that produces a number; everything after it is shaped by that number.

## 7. What hypswarm is not

Not a chat framework, not a prompt library, not a place where state lives. If a feature needs the agents to
remember something the record doesn't hold, the record is missing a node type, and that is where the fix goes.
