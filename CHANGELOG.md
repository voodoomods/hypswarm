# Changelog
 
## Unreleased

- **A stage that reads the code doesn't go to the seat that changes it.** The seat a workflow names for its change
  stage (software: the implementer, on `diff_registered`) isn't the fallback for another stage, and those orders
  say not to edit the working files. With the tester busy, a counting question went to the implementer, who
  rewrote the code under test; the new head made every check stale and nothing settled.
- **A value in seconds is a timing only when the code measures time** (`perf_counter`, `timeit`, …). A duration
  that is the data (`parse_duration("2.6s")` returns 2) re-runs to the same digits; it was refused for a spread.
- **A review order says what an objection is for:** the answer, a number in the claim or the method being wrong;
  a wording point goes in the notes of a `checked`. "Judge the method and the wording" drew objections to right
  answers whose numbers reproduced, each a full rework.
- **`hypswarm run --python`** gives the seats a python tool in `--folder` and re-runs every registered computation
  with it (the instrument): a subprocess with a time limit on your machine, not a security boundary
  (`hypswarm.sandbox.python_subprocess`). A scientific, software, trading or optimization run with nothing that
  executes code is told so up front, seats included. Through the CLI with only the files toolkit, an
  optimization run's seats wrote "exact DP over capacity" as prose and a wrong optimum settled.
  With no instrument and only the files toolkit, `register_run` refuses code: nothing could have run it (the
  same run registered code and its "output" 14 times).

## 0.1.0a8 — 2026-10-27: measure questions, and the lead writes the report

Needs hypgraph 0.7.0, whose workflows let a question that asks for a measurement skip the gates it doesn't need.
Found in real-model runs of harder tasks (a bug fix, a speed claim, a flaky test, a spec check, Simpson's paradox,
a look-ahead trap).

- **Measure questions.** A task question may be `(code, text, "measure")` (`asks = "measure"` in a `.toml` task): it
  asks for a number, a timing or a check of what exists, and the record's workflow skips the change, hypothesis and
  backtest gates it doesn't need. Before, a timing question was reworked for a diff, a count for a preregistered
  hypothesis, a look-ahead check for a backtest.
- **The lead writes the report.**
  - The last report turn offers only `submit_report`. A refused submit there gets one retry with the refusal in hand,
    and a turn with no call goes straight to that last turn.
  - The prompt says answers copy the numbers the record binds.
  - `Budget(report_calls=8)` (at most a fifth of `max_calls`) holds the last calls for the report. The stop reads
    "budget: only the report's calls are left".
- **Measurements the instrument can check.** A result value may state its `spread` (or `rel_tol`), and the
  instrument confirms a re-run inside it. `register_run` with code refuses a timing that has none, and says how to
  give it.
- **The software workflow watches the tree by default.** While it watches, a seat can't register its own diff: edits
  register the next head. Two competing lines of heads had come from both.
- **A question isn't an order.** The lead's `add` refuses question text with no "?" and points at `rework`.
- **Reviews land.**
  - A review method past the record's 1,500 characters spills into notes instead of losing the review.
  - The reviewer's prompt says the verdict is the deliverable: re-run with `register_run`, then `review`.
- **The examples' sandbox writes scratch outside the watched tree,** and keeps `SYSTEMDRIVE`.
- **hypswarm.com in the HypGraph app's design system,** the same stylesheet as hypgraph.com, light by default, across
  every page. The homepage opens on the Live view of a HypSwarm run replaying (one per profile, `dev/site_examples.py`),
  and can switch to the page's own record.
- **The homepage proves its figures with its own HypGraph record** (`dev/site_record.py`, run at every deploy):
  tests passing, runtime dependencies, how many of the five example runs settled, and how many writes the record
  refused in them. The lab reads each run's telemetry; a reviewer re-runs the five examples from scratch and reads
  each record's completion and refusal log. The page's text is checked against the record with `hypgraph check`, and
  a copy error fails the deploy. `dev/build_site.py` copies the HypGraph UI from the released `hypgraph`.

## 0.1.0a7 — 2026-10-26: watch a run

Needs hypgraph 0.6.0, whose HypGraph UI streams the telemetry into its Live view and replays a finished run
(`hypgraph export --telemetry` carries it in a bundle).

- **"Atlas" is now the HypGraph UI** in the examples, their READMEs, the site and the design notes, as in hypgraph
  0.6. The examples point to [hypgraph.com/examples](https://hypgraph.com/examples/), where 01–05 replay live.
- **Telemetry: everything a run does that the record can't see** (`telemetry.py`). Every model call, tool call, work
  order and scheduler decision, as spans (run → order → model / tool), with tokens in, cached and out, $ at the run's
  pricing, seconds, ok or error, and the tool calls each reply asked for.
  - **Where it goes:**
    - A record file gets `<record>.telemetry.jsonl` beside it by default (`run(..., telemetry="auto")`); a path writes
      elsewhere, and `False` is off. `hypgraph serve` streams the sidecar into its Live view, so a running swarm is
      watched call by call.
    - `otel=True` also sends OpenTelemetry spans with `gen_ai.*` attributes, plus metrics for calls, tokens and $,
      through whatever tracer and meter your process configured. Install with `pip install 'hypswarm[otel]'`.
  - **What it holds:**
    - By default no reply text, tool argument value or output is written: arguments are summarised as names and value
      types. `capture_content=True` adds them, truncated.
    - Secret-looking strings and secret-named arguments are scrubbed either way.
    - Agent seats from other frameworks are traced too. Their tools are wrapped with the order's span captured, so a
      tool run on the framework's own thread is still traced, and their model use is one span with the usage they report.
    - A broken sink never breaks a run.
  - `RunResult.telemetry` names the sidecar written.

## 0.1.0a6 — 2026-10-26: the report from the record, re-verification per value

Needs hypgraph 0.5.3 (a result that names no file it read goes stale when an input file changes after it).

- **The harness writes the report when the lead's doesn't pass** (`assemble.py`, `run(..., assemble_report=True)`,
  on by default). A run can end with a current, checked claim on every question and still lose its report, because
  the lead never submitted one the record's check accepts. The harness now writes it from the record alone: the
  facts, a labelled note, and an answers block read off each question's current claim — the fields the question
  asks for, filled only from what the claim binds (or, for a claim that binds nothing, the current results it is
  derived from); a true / false field only from a boolean, never a 0 that an author labelled "optimal"; a stale or
  contested claim answers nothing. The text has to pass the record's check like any report. No model call.
  `RunResult.report_source` / `SchedulerResult.report_source` say whose report it is (`lead` | `assembled`);
  `report_accepted` still means the lead's passed. Replayed on the change suite's 13 lost reports: 11 assembled,
  none stale, no field filled with a wrong value.
- **Re-verification per value.** When one value of a stale result moved, a claim whose own values all reproduced on
  the current files now comes back: the instrument files a result of just those values that supports it, so a claim
  about A's count isn't redone because B's moved in the same run. What a claim rests on is its measurements bound to
  that result; for a claim that binds none, the values its statement states, only when every number in it is one
  of them. Any other bound result must itself be fresh. Replayed on the change suite's stored re-executions: 6
  claims would have come back, all with the post-change values, saving 2 of the 11 redos of untouched questions.
- The change-suite runner logs every call of the tools both conditions share (`tool_calls`: what ran, what it
  printed, whether the change had fired), so an odd run can be read back.
- The change-suite runner keeps `report_source` and scores an assembled report beside the locked score (which counts
  only the lead's).

## 0.1.0a5 — 2026-10-26: when the world changes (P3)

0.1.0a4 was tagged but never published: `__init__.__version__` still said 0.1.0a3, and the release workflow
publishes only when the tag matches it. 0.1.0a5 carries everything 0.1.0a4 described (orders from stages) plus the
P3 instruments; a test now keeps `pyproject.toml` and `__version__` equal.

The record now notices when the files and pages a run used have changed — nobody has to tell the team.
- **The world watcher** (`world.py`, `run(..., watch=True)`). Each scheduler round re-hashes the task's files: a file
  whose bytes changed gets a new artifact that supersedes the old one, so every result computed from the old bytes
  goes STALE. Under the software workflow the working tree is one `kind=diff` head that a commit supersedes — tests
  on the old head stop counting. With `refetch(url) -> text`, each source's page is fetched again and filed as an
  `excerpt` (hypgraph 0.5.2); a page that no longer says the passage makes the source stale. Each change becomes a
  notice in every later order and the lead's prompts.
- **Re-verification on the current files.** Every stale result is re-run once per reason by the instrument; when every
  registered value reproduces, the lab result supports the claims built on it and they are fresh again with no model
  call; when a value moved, they stay stale and the question is redone. The instrument's run `uses` the live version
  of each file the author's run used.
- **Refresh orders.** An answer whose evidence went stale gets a worker order to recompute and write the claim again,
  not a review — a check of stale evidence can't count. Review stages pick only fresh claims and results.
- **Implied `uses`.** `register_run` links the live file artifacts its code names and the question's current diff or
  instance, so freshness works without the model declaring what it read.
- `on_write(kind, payload)` hook on every accepted seat write; `SchedulerResult` counts `world_changes`,
  `reverifications`, `refreshes`. The examples' scripted seats read notices and refresh orders and recompute once the
  world moved under their question.
- **The change suite** (an internal study): five families where a file, a commit, a page or an instance changes
  silently mid-run.
- Depends on hypgraph >= 0.5.2.

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
