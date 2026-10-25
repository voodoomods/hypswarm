# ADR-007 — The instrument reproduces; reviewers judge; a result and its claim are one write

**Date** 2026-10-25 · **Status** accepted · **Measured cause** harmony confirmatory, 142 runs

## Context

Where a record run's model calls went (per run, condition C / D / E): the reviewer 47 / 34 / 28, re-deriving every
number with its own python; 31 / 18 / 16 `graph_add` for four or five claims (eight refusals a run, each a model
round trip to learn which number was wrong); 21 / 16 / 13 `register_run` for four results; 16 / 11 / 13 `show`
reading back what the tool reply had already said; 3 / 2.4 / 0.4 units at the 14-turn cap. The record held every
number and the code that produced it, and paid a model to compute it a second time.

## Decision

1. **The instrument re-executes registered code; no model recomputes it.** `register_run(code=…)` stores the source
   on the run (`config.source`). The scheduler, when the host supplies a `reproducer(source) -> stdout`, re-runs
   every such result once before any review and files a `kind=lab` run by the instrument that `replicates` the
   author's run (`differs: same_code`) with a result: *all registered values appear in the output* or *missing: …*.
   The author's result gains `reproduced in project` evidence; the review order names the replication and says
   "judge the method and the wording; recompute only what is not reproduced". The host decides where code runs
   (the same sandbox its workers use); hypswarm executes nothing itself.
2. **A result and the claim it supports are one write.** `register_run(…, claim=, answers=, scope=)` creates the run,
   the result, and a claim `derived_from` and `supported by` that result, its numbers bound by the engine's
   auto-binding. One call where there were three (register, add, retry after the refusal).
3. **The order carries the target** (HypGraph `coord.order_text`): a claim's statement, scope, measurements and the
   values of the results it rests on; a result's values; a question's text; an experiment's protocol; and the
   replication, when there is one. `show` becomes unnecessary for the common case.

## What it does not do

- It does not verify *correctness* of the method — only that the code, re-run, prints the registered numbers.
  A wrong method reproduces perfectly. That is what the reviewer's judgement is now for.
- A value that only appears in the output rounded differently than registered is "missing"; the author should
  register what the code prints.
- The study's A–D runner is unchanged (preregistered); condition E takes the reproducer under a deviation (D-19).

## Alternatives considered

- Telling the reviewer not to recompute: the pilot prompts already said to check against the record; the
  reviewers recomputed anyway. A rule the record enforces beats a rule in the prompt (the same lesson as the
  04 study's checks).
- Structured comparison of returned values instead of "numbers appear in stdout": needs every script to return a
  dict in an agreed shape; agents don't do that reliably, and the output-match is the honest minimum.

## Consequences

- Tests (`tests/test_reproduce.py`): both workers register result + claim in one call; the instrument re-runs
  both (two `reproduced` events, two `kind=lab` runs with `replicates`), the claim's evidence is `project_rerun`,
  every review order says "reproduced"; a registered number the code does not print is *not* reproduced; the
  stub run makes the same 12 calls as before (the scheduler's work didn't grow).
- Expected on real models, to be measured against the confirmatory numbers: critic ≈ 47 → 10, `graph_add` ≈ 31
  → 8, `show` ≈ 16 → 2 — C from ~107 to ~45–50 calls a run, E lower still. Still above A's 18: on tasks this
  size a single agent is cheapest, and the record's case is the long-horizon, many-hand-off one.
