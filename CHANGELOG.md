# Changelog

## Unreleased

Found running the harder challenges on gpt-oss-20b on a local BC-250.

- **Test runs reach the instrument.** The software prompt asks for the exact test command, and seats gave it:
  `python -m pytest test_x.py` ran as Python source, a SyntaxError on every re-run. A test run registered with no values
  got "0 of 0 confirmed", inconclusive. Neither ever met `tests_pass_current`, so both code-fix challenges settled
  nothing. A one-line python or pytest command now runs as that command, in the tool and on the re-run, and the
  instrument reads the runner's own summary when it has no value to confirm. Failing tests are negative, and "0 passed"
  is not a pass.
- **A worker's last three turns only write.** Orders ran out of turns 60 times in 16 runs, 826 of about 1,900 calls,
  usually on a refused write and sometimes having written nothing. The last three turns offer `register_run`,
  `graph_add`, `graph_link` and `return_work`, and say why.
- **A settled question stops looping.** A question the board calls settled ends the run's work on it, and a stage that
  can't move after one repair order is marked stalled instead of repeating.
- **A review reads how the numbers were computed.** A re-run shows the code printed a value, not that it computes the
  right thing: a hand-rolled exact test printed p=0.018 (true 0.08), the instrument confirmed it, and a wrong answer
  settled. The review order now says so and asks for any p-value to be worked out a second way.
- **A review objects to a claim that doesn't state its answer**, such as "it opened on a date".
- **Tools take the calls seats meant.** `graph_add` accepts `register_run`'s field names and drops measurements it
  can't read, takes a scope from the linked result, and defaults a hypothesis to the order's question; `register_run`
  finds the order's open experiment, leaves out a `uses` the record doesn't hold, and moves a retry onto the seat's own
  result. A run named as `supports` means its result. Every check still runs on what's passed on.
- **A report needs its answers block.** gpt-oss put Python in `submit_report`'s text, and 4 of 17 runs ended on a
  "report" that was a code snippet: with no claim in it, the checks had nothing to refuse. When the task asks for an
  answers block, a report without one is refused, and the harness assembles one if the lead can't.
- **Knowledge seats check a source's standing.** A run settled a retracted census figure: nobody opened the archive's
  list of retractions, and a review objecting to "no source found" sent the researcher to the withdrawn survey. The
  note now says a retraction outranks the source it names and a primary source outranks a later summary.
- **A test run brings its own count.** `register_run` takes `tests_passed` {k, n} and the outcome from the test runner's
  summary, and a claim that rules on all of a run is bound to that count. "All tests pass" had nothing behind it and was
  refused about 12 times in 3 runs while the question stayed open. On 3 of 6 the record now refuses it as false.
- **A withdrawn source is found wherever it's named.** The check read only `url`; a source naming its file under `doi` or
  `citation` got past it.
- **A claim about the original can't rest on a run of the current files.**
- **A rework says what it already has.** A rework that only lacks the claim now names the numbers already measured and
  asks for the claim, instead of the seat recomputing them until its turns run out.
- **A different draw isn't an objection.** A reviewer objecting to a number the instrument found varies from run to run
  is told so once; a second objection goes through.
- **Fewer refused calls:** `url|doi` is read as a url or doi, and `graph_add(type="diff")` as an artifact.
- **A run on the kept files doesn't rest on the head.** A fix no longer makes results about the original stale.
- **A server still loading its model is waited for**, up to 15 minutes, instead of ending the run.
- **A sampled number isn't a contradiction.** When a re-run prints a different number next to a value's name, the
  instrument runs the code twice more. If the runs differ among themselves and the author's value is near them, the
  value is reported as varying instead of contradicted, and a review is told that a different draw is no objection.
- **A withdrawn file can't be cited.** `graph_add` refuses a source whose file another file in the folder withdraws,
  and names the line. The note about retractions alone didn't get RETRACTIONS.md opened.
- **The original stays runnable.** A run measured "the original" on the code it had just fixed, got 0 repeats where the
  truth is about 98 in 1,000, and a reviewer passed it. `Task.baseline` now defaults to on for a software run with a
  folder, and `register_run` refuses code that runs a kept file for a question about the original instead of its copy
  under `_base/`. A bare `pytest` no longer stops on both copies of a test file.
- **Refusals say how to fix them.** `submit_report` gives each finding's message, and `show` says a file isn't a node.
- **The software note matches the tools.** Under watch the record registers the diff, and the note no longer asks for
  one the tool refuses.

## 0.1.0a13 — 2026-11-05: a report can't call a checked answer unanswered

- **A report can't say null over a checked claim.** null means no claim answers the question, but a lead that found
  a null effect wrote `"Q2": null`, so the answers block read as unanswered beside a checked claim that said "not
  significant" (4 of 13 gpt-oss runs of one task). `submit_report` now refuses an answers block that leaves null, or
  leaves out, a question with a checked, current claim, and `ANSWER_FORMAT` says a negative answer is false or "no".
  The refusal also applies where a claim's finding is that nothing was found: write that finding, not null.
- **An assembled report gives the claim's own sentence** when a current claim binds nothing the question asks for. It
  used to answer null there too.
## 0.1.0a12 — 2026-11-04: gpt-oss runs a swarm on local hardware

Needs hypgraph 0.8.4. Measured on gpt-oss-20b on a local llama.cpp server, example 01's task: on hypgraph 0.8.4, 3 runs
settled 6 of 6 questions in 3.3-8.9 min, with no failed calls and no wrong answers. On hypgraph 0.7.7, 5 runs settled
9 of 10.

- **gpt-oss gets its own reasoning back on tool calls.** The harmony format needs it. `OpenAICompatible` dropped
  `reasoning_content`, and the model then wrote broken channel headers (llama.cpp HTTP 500) or degenerate text; a
  replay of captured requests failed 7-17 of 24 times under every server and sampling setting, and 0 of 24 with the
  reasoning sent back. On by default when the model name contains `gpt-oss`; `return_reasoning=` or
  `--return-reasoning on|off|auto` overrides it.
- **Code registered after a bare result becomes that result's code.** A seat that registered a number with no code
  could never put code behind it: the gate wanted a re-runnable result and a new one was refused as a restatement, so
  it filed copies of its claim until the budget ran out. The run now attaches to the old result, and the instrument
  re-runs the code against that result's values. A result that already has code is still a restatement.
- **A copy of an answer is refused.** The record holds a question at "answered" until every answer is checked, so a
  seat's copy of its own live answer only delays settling. The refusal says to revise the old claim or return the
  order. A claim with a different figure is allowed.
- **A refusal is relayed once.** `register_run` with a claim returned "claim refused: claim refused: …" — the
  record's own prefix repeated — in the seat's reply and in the Live view's event stream. hypswarm.com's
  embedded Live view passes `embed: true` (hypgraph ≥ 0.7.6), so its feed stays short.

## 0.1.0a11 — 2026-10-28: the files as they were at the start stay readable

- **`Task(baseline=True)`: the files as they were at the start stay readable.** They are kept under `_base/` and
  registered as artifacts of kind `baseline`, which the watcher never supersedes and the tree head never counts. A
  question about the original ("which tests fail on the original semver.py?") is answered from them after a seat
  has changed the working files, whose own artifacts the watcher supersedes. Until now the tester's scratch copy of
  the original was refused as unregistered and the record's original artifact had been superseded, and the question
  stayed open in every run of the challenge (E1, stuck in 2 of 2 runs after every other fix).
 
## 0.1.0a10 — 2026-10-28: a label in a count's clothes can't crash a run

Needs hypgraph 0.7.2: the claim checks that accept the honest sentences agents were writing (absolutes over a set
the sentence counts, "no difference remains significant after correction", a p-value found by its key's tokens, a key
beside its value, the instrument's re-executions), `UNCORRECTED_EFFECT` (a nominal effect can't hide its correction
in the scope), and `VALUE_NOT_A_NUMBER` (a result value's `k` and `n` must be numbers). Measured on one run of each
of sixteen challenges across the five profiles: refusals per run 6.6 → 4.9, nothing settled wrong.

- **A registered value that isn't a number is skipped, not fatal.** A quant registered
  `{"k": "40/50", "n": "rank 1 of 20"}` as a result value — a grid setting and its rank in a count's clothes. The
  instrument's reproduction did `float()` on it and took the run down at its very end, after every order had
  returned. `reproduce.check_output` now reproduces a `k` / `n` / `value` only when it is a number (int or float,
  not a bool), and skips the rest as it skips unprinted values. The record side refuses such a value at write
  (hypgraph 0.7.2, `VALUE_NOT_A_NUMBER`).

## 0.1.0a9 — 2026-10-27: the new-user path works, and a computed answer needs its code

Needs hypgraph 0.7.1, whose optimization, trading and scientific gates settle a computed answer only with the code
behind it. Found in an evening of real-model runs across all five profiles, scored against their answer keys, and in
a new user's walk through the README and the CLI.

- **A stage that reads the code doesn't go to the seat that changes it.** The seat a workflow names for its change
  stage (software: the implementer, on `diff_registered`) isn't the fallback for another stage, and those orders
  say not to edit the working files. With the tester busy, a counting question went to the implementer, who
  rewrote the code under test; the new head made every check stale and nothing settled.
- **A value in seconds is a timing only when the code measures time** (`perf_counter`, `timeit`, …). A duration
  that is the data (`parse_duration("2.6s")` returns 2) re-runs to the same digits; it was refused for a spread.
- **A copy of a question with a clause added is a copy.** The lead's `add` refuses a question that holds 90 % of
  an existing one's words ("… or decline — given the honest out-of-sample result …" for Q3), as well as one that
  overlaps it by 80 %.
- **Every unchecked answer gets its review under a workflow.** A seat working on Q1 also answered Q2; that claim
  was in no gate's evidence, so the review stage could only go to the newest claim (already checked) and the run
  stopped stuck with Q2 held open. The review stage now takes the board's unchecked answers too.
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
- **A seat that returns at no cost can't keep a run alive.** Nothing is dispatched once only the report's calls
  are left, and a seat whose orders end in an error three times in a row is benched for the run (`benched`
  events, `SchedulerResult.benched`). A crashing agent spends nothing, so each return was reworked or cancelled
  for free; once the record's clock moved, a fresh order was issued and the run never ended (it hung CI on a
  slower runner).
- **`pip install --pre hypswarm` works again.** `--pre` reaches every dependency and resolved httpx 1.0.dev6,
  which has no `AsyncClient`: the CLI crashed on its first model call. httpx is now `>=0.27,<1`, and CI installs
  the built wheel the way the README says, in a clean venv, and constructs the provider.

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
