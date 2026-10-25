# ADR-005 — Reviewers review; an unreviewable answer goes back to a worker; the report phase only reports

**Date** 2026-10-25 · **Status** accepted · **Found by** pilot 4, condition E, both F7 instances

## Context

Both hypswarm runs on the F7 instances ended `stuck` with no report, after every order had been accepted or
cancelled. The record showed why: the **critic** — the only reviewer seat — had written the claim that answered a
question (CL5 on F7-907, CL8 on F7-906) while holding a review order. The scheduler excludes a claim's author
from its reviewer pool, so the pool was empty, no review could be issued, the question stayed `answered`, and
`_done` reported `stuck`. The lead then spent all six report turns planning (it added a question explaining what
should happen) and never submitted, so the run returned the facts without an answers block and scored 0.

Nothing in the record was wrong: a reviewer is allowed to write claims (a human reviewer sometimes should). The
gap was the scheduler's: it let a role do something it could not then follow through on, and it had no move for
the state that produced.

## Decision

1. **A reviewer seat's `graph_add` refuses claims.** The reply says to record a verdict instead and to note a
   missing answer in the review, so a worker gets asked. Results and runs are still allowed (a reviewer may
   recompute). This is a seat rule, not a record rule: the record stays permissive for humans.
2. **An unreviewable answer is re-issued.** When the only live answer to a question was written by every available
   reviewer, the scheduler issues a worker order for the question — "write the answer as your own claim" — and
   emits an `unreviewable` event, instead of waiting on a review nobody may write.
3. **The report phase gets `briefing`, `report_facts`, `show`, `submit_report` only.** Planning tools (`add`,
   `rework`, `cancel_work`) are for exceptions mid-run; at the report the run is ending and nothing added will be
   worked. Refusals of the report are counted (`report_missing` event with the count) so a run that ends without
   a report says so in its events, not only in its score.

## Alternatives considered

- Letting a second reviewer review the first: needs a second reviewer seat on every roster; a single-reviewer
  swarm is the common cheap shape.
- Having the harness accept an unreviewed claim after a timeout: that is the record pretending; a question
  settles on a checked claim or it doesn't.
- Giving the lead more report turns: the lead wasn't short of turns, it was using them for the wrong thing.

## Consequences

- Tests (`tests/test_roles.py`): an eager reviewer's claim is refused and the run still settles; a record where
  the critic already answered Q1 (as an outside seat could) resumes, re-issues Q1 to the analyst, and settles on
  the worker's reviewed claim; the report-phase tool list carries no planning tools.
- The F7 failures in pilot 4 are reported as what they were — a scheduler gap, not a model failure — and
  condition E is rerun on those instances only after this change (recorded as a deviation).
