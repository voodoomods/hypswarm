# ADR-002 — The harness is a reserved author, and a served record needs a token

**Date** 2026-10-25 · **Status** accepted · **Review finding** #2 (high) · pairs with HypGraph ADR-001

## Context

In server mode every worker — and any outside seat on MCP or HTTP — talks to one record. The scheduler writes as
`harness`: it issues every order, settles accepted work, reworks and cancels. Nothing stopped a client of the
served record from writing as `harness` too, because the engine's reserved set didn't include it.

## Decision

- `LocalRecord` builds its `Policy` with `extra_reserved={"harness"}`. On the served copy, `harness` is refused
  to anyone whose token doesn't name it; in-process, nothing changes (the scheduler is the only caller).
- `HttpRecord(url, token=…)` sends the bearer. The swarm's token is bound to the harness **and** its seats, since
  this one client writes as each of them. An outside seat gets a token bound to its own name.
- `AuthError(GraphError)`: 401, and 403s that are about the token, raise as an identity refusal. Callers that
  catch `GraphError` still work; callers that care can tell the two apart.
- `Seat.RESERVED` already refused `harness` as a seat name; that stays.

## Consequences

- `hypgraph serve --writable --token SWARM=harness,analyst,stats,critic,lead --token NIC=nicolas` is the shape of
  a shared record: the swarm on one token, a person on another.
- A served record without tokens behaves exactly as before (and is documented as localhost-only).
- Tests in `tests/test_auth.py`: the swarm settles on its token; no token / wrong token raise `AuthError` before
  any write; an outsider's token cannot `start` (which writes as the harness) or `issue_work` as the harness.
