# ADR-001 — The budget counts calls in flight

**Date** 2026-10-25 · **Status** accepted · **Review finding** #1 (high)

## Context

`Meter.check()` looked at completed calls only. Workers run as parallel asyncio tasks, and a provider call takes
seconds, so with one call left every idle worker passed the check and every one was billed. Measured on the stub
task with five workers and a cap of three: **seven** calls were made. The budget was described everywhere as a
hard rule; it was a soft one by up to the number of parallel seats.

## Decision

A call is **reserved** before it is made and **consumed** when it completes:

- `Meter.reserve(unit)` runs the check *including* reservations, then claims one call for the run and the unit;
  it is synchronous, so under asyncio there is no await between the check and the claim.
- `Meter.add(...)` consumes a reservation for that unit if one exists (legacy callers that never reserved still
  count correctly).
- `Meter.release(unit)` returns a reservation whose call raised.
- Dollars in flight are estimated at the running average cost per completed call; a dollar cap therefore refuses
  the call that would, on average, cross it, instead of discovering the overshoot afterwards.
- `calls_left()` subtracts reservations, so what a worker is told in every reply is what is really left.

The worker loop and the lead's turns use `reserve` / `add` / `release`. `check()` keeps its signature.

## Alternatives considered

- A lock around check+call+add: serialises every model call — a 5-seat swarm would make calls one at a time.
- Counting only completed calls and accepting the overshoot: contradicts the contract the budget states to every
  seat and to the operator.
- Reserving dollars by a fixed per-call maximum: needs a number nobody has before the run; the running average
  is what the run itself has measured, and it is conservative once the cheap first calls are behind.

## Consequences

- Five parallel workers with three calls make exactly three (`tests/test_budget_concurrency.py`).
- A reservation held by a worker that never completes (a hung provider) is released by the worker's own error
  path; a hard kill of the process loses nothing because the meter is in-process state that dies with it.
- The per-order cap now also counts a reservation, so two concurrent turns of one order can't both pass with one
  call left on it (an order runs in one worker, so this is defence in depth).
- Measured: the full test suite is unchanged in count and wall time; the stub benchmark makes the same number of
  calls (the race never occurs there because the stub completes without yielding).
