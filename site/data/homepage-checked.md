<!-- the homepage's text as `hypgraph check` read it, figures filled in from the page's record (dev/site_record.py) -->

id="main">

v0.1.0a7 alpha
built on HypGraph Open source · Apache-2.0
Python

Many agents. One record.

HypSwarm runs one agent or a swarm of them on a research, engineering, trading, knowledge or
optimisation task, with a HypGraph record as the only shared state. The record
schedules the work, accepts it against predicates it checks itself, re-runs what the authors computed, and writes
the report. Models do the work and judge exceptions; what counts as done is the record's rule, not a line in a prompt.

Watch a swarm work Run a swarm
Take a seat

verifying…

Two ways in

Hold a seat, or run the swarm.

For agents & people

Take a seat

A seat is a name in the record. Hold it over MCP from Claude Code, Cursor or any client: the scheduler issues
you orders, each reply says whether your order is done, and the record holds you to the same rules as the
other seats, whether you're a person or a model. Machine-readable: .

The how-to for agents & people

For engineers

Run a swarm

A task, a profile, a budget. The roster comes with the profile, the tools from a registry you control, the
scheduler ,
workers hold no state, and the record is the audit log. Any OpenAI-compatible endpoint, Anthropic or Bedrock.

The how-to for engineers

What you can check

Facts, each with its source.

Each figure here is a claim in this page's own HypGraph record, bound to the measurement it came from
and re-measured another way by a reviewer before the page was built. Click a claim to open it in the record.

Tests
80 of 80
passing on this build; 4 skipped here (optional extras not installed)

Runtime dependencies
2
and

Example runs settle
5 of 5
the five above, one per profile, on scripted models

Writes refused in those runs
6
by the record, as they were written; each run still settled

The record is the orchestrator

What a run looks like when nobody has to coordinate.

The scheduler issues an order per open question to the seat that fits; workers write runs, results and
claims; the instrument re-runs each author's code; the record accepts each order once its predicates are met; a
reviewer's check settles each question; and the lead writes the interpretation under the facts.

Order
A task node: the target, premises pinned to their versions, done-when predicates, a budget and a lease.

Write
Runs with their code, results with values, claims with numbers bound to them, checked as they're written.

Reproduce
The instrument re-runs the code: each value confirmed, not printed, or contradicted, with no model in the loop.

Settle
Predicates met → a decision on the evidence; a reviewer's check settles the question.

scheduler
Code, not a model
Issues from the question board, settles met
orders, reworks the rest twice, cancels what became moot, escalates at exceptions.

instrument
Reproduce, don't recompute
A registered run's code is
re-executed in your sandbox before review; a reviewer recomputes only a contradicted value.

workers
Stateless
A worker's context is its order and its own turns.
Kill it and the lease expires; a run that died resumes from the record.

budget
A rule, not a hope
Calls and dollars, per run and per order,
counted with calls in flight, enforced by the scheduler and shown to each seat in each reply.

Profiles

Five disciplines. One record. The record decides what counts.

A profile is pinned on the investigation and versioned: what the record refuses as it's written, who
sits at the table, what complete means, and the discipline's workflow — the stages a question passes through and
the gate out of each. The record won't take a write that breaks it, so none of it depends on a prompt being followed.

scientific
analyst · stats · critic · lead

A hypothesis with predictions; an experiment preregistered before a run; numbers bound to measured results; a
reviewer's check on fresh evidence settles it.

refuses a number with no result behind it · without the count · without the test

software
implementer · tester · reviewer · lead

The change as a diff by hash. A pass is the instrument's run of the tests on that head, a lab-recorded result,
not a report of one. A newer commit supersedes the diff and its tests go stale.

refuses without an instrument run, or on a superseded head · the diff's author as its reviewer

trading
quant · risk · lead

A thesis is a hypothesis; the backtest is preregistered. An edge is out of sample, after costs, with the
configurations tried declared. A position has size, stop and review date — paper, or declined.

refuses a backtest without its costs · in sample · a position without a stop · a live order

knowledge
researcher · fact_checker · lead

A source carries the passage that says it, when it was read and what kind it is; the claim cites it; the
fact-checker opens it. With no source, a checked inconclusive answer settles the question.

refuses a claim from recall · a source without its passage

optimization
modeller · solver · verifier · lead

The instance by hash; the model as a hypothesis; a result with the objective, its feasibility and a bound or
gap; the verifier recomputes feasibility before the claim.

refuses an objective without feasibility · without a bound

yours
one Profile · one Workflow · one roster

Vocabulary, predicates, refusals, completion criteria and a workflow are one object in HypGraph; a roster and
its toolkits, here. The scheduler issues whatever stage the record names.

see

Seats, not personalities

Roles the record can check.

A seat is a declared capability bound to an author name in the record: a role, the words it
, the toolkits it may use, a model, and optionally a deeper one to escalate to. Each profile
brings a roster; yours overrides it.

worker
Takes orders from the board; writes a result and its claim in one call, with
the code; returns when the record says the order is done.

reviewer
Takes review orders, and its verdicts count — not on its own work. It writes
verdicts, not claims.

lead
Called at exceptions — an order stuck after two reworks, a contested claim — and
for the report's interpretation.

instrument
Not a model. Re-runs registered code in your sandbox and files
lab-recorded runs, so a pass is its finding, not the author's.

external
A person or another agent holding the name over MCP. Orders come to it like any
seat; when the lease runs out, the record returns the order.

operator
A person, reached through the record: approves budgets, answers
escalations, holds the tokens that bind writes to names.

Watching a run

See each model and tool call as it happens.

A run writes its telemetry beside the record: each model call, tool call, work order and scheduler
decision, with tokens, cost and timing. Serve the record and the HypGraph UI's Live view shows which seat is
calling the model or running a tool right now, what each has spent, and where a work order's time went — the
view at the top of this page. sends the same spans to OpenTelemetry; prompts and replies
stay out unless you turn them on.

watch it live

replay it anywhere

For agents & people

Hold a seat over MCP.

The HypGraph MCP server is the interface. shows your open orders, with each
predicate and how to meet it. You register runs with their code, record results, make claims; each reply says
whether the order is done; you return it.

If you are an agent reading this. Call . Do what the order says,
from the files, with the tools you have. Register the exact code you ran and print each value you register, with
its name: the instrument re-runs it. Write a claim's numbers from a result; a refusal tells you the honest
version. When the reply says the predicates are met, call and stop there.

The full how-to for agents

seats.toml

your side

For engineers

A task, a profile, a budget.

pins the governance profile and brings its roster;
is how your sandbox, data access and CI become tools. Tools that execute code or
reach a network don't ship in the box, and a profile that asks for a toolkit you haven't registered fails loudly.
Workers can share one process or talk to a record served with token-bound writes; a run that died resumes from
the record.

The full how-to Source & README
Design decisions

python

This page has a record

We hold this page to the rules it describes.

The figures above are claims in a HypGraph record built with the page. The build's instrument measures
them, a reviewer re-measures each another way — the tests run again, the example runs started fresh — and the
page's text is checked against the record with . Open it in the app above with
This page's record , or download the bundle .

Status

Alpha.

The API may change between alphas; each release is tagged, tested in CI, and published to PyPI by
trusted publishing. Built: the scheduler that issues each question's stage order, workers, five profiles with
rosters and workflows, the tool registry, agent seats for LangChain / LangGraph, PydanticAI and CrewAI, external
seats over MCP, token-bound writes on a served record, resume, escalation, instrument reproduction, verified file
tools, telemetry with optional OpenTelemetry, model adapters for OpenAI-compatible endpoints, Anthropic, Bedrock
and LangChain, and ten runnable examples. Design decisions are written down in
docs/decisions .
