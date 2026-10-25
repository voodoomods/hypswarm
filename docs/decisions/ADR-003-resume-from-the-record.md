# ADR-003 — A run resumes from the record, not from memory

**Date** 2026-10-25 · **Status** accepted · **Review finding** #4 (medium)

## Context

The scheduler kept its working state — which seat holds which order, how often an order has been reworked — in
process memory. A crash, a kill, or a provider stall that the host had to cut short left orders open and targets
leased in the record, with no way to pick the investigation up again: `run()` could only seed a new one.

The record already held everything the scheduler knew: orders are task nodes with assignees, rework chains are
`supersedes` links, returns are lease-release events. State that is derivable from the record should be derived
from it.

## Decision

`run(..., resume=<investigation>)`:

- the task is **not** seeded again; the investigation is resolved from the record and checked to be one;
- a new **run node** is filed with `config.resumes = <inv>`, so the record shows two runs on one investigation
  and which resumed which;
- before the first round, `Scheduler._adopt()` takes over every `open` / `overdue` order: it follows the
  `supersedes` chain back to the first order (that depth is the rework count, so the cap and model escalation
  carry over), dispatches the order to its seat (one per seat; the rest wait for a later round), and **cancels**
  an order whose assignee has no seat in this run, with that reason;
- returned orders need no adoption: the first round's settle / rework handles them as usual.

A worker re-dispatched this way sees the order text afresh; the writes it made before the crash are in the
record and still count toward the predicates (they were written after the order was issued).

## What it exposed in the engine

Cancelling an open order left the target leased to the old assignee for the lease's remaining hours, so the
resumed run could not re-issue the question to the replacement seat and ended `stuck`. `coord.cancel_work` now
releases the lease when it was taken for that order (HypGraph, with a test); a returned order has already released
it, so nothing changes there.

## Alternatives considered

- Checkpointing scheduler state to a file: a second source of truth beside the record, which would drift.
- Letting leases expire and re-issuing from the board: loses the rework count (an order on its third attempt
  would get two more), and waits up to four hours.

## Consequences

- Tests: a run that died with one untouched order and one reworked order resumes, adopts both (`T1` at 0 reworks,
  `T3` at 1), settles, verifies, and the record shows one investigation with the resuming run filed; a resume with
  a missing seat cancels that seat's order and finishes through the replacement.
- `SchedulerResult.adopted` and `adopt` events make the takeover visible.
- No change to a fresh run: `adopt` is only called when `resume` is given.
