# ADR-008 — Profiles bind a roster and toolkits to the record's governance; tools come from a registry

**Date** 2026-10-25 · **Status** accepted · pairs with HypGraph ADR-002

## Context

hypswarm had three seat roles the scheduler acts on (worker, reviewer, lead), a free roster, and tools passed as a
list of Python functions. That is enough for one domain. Branching into software, trading, knowledge and
optimisation needs each domain to say who usually sits at the table, what they hold, and which record rules they
work under — without the roles multiplying (the roles are what the scheduler can *check*, not job titles).

## Decision

- `Task(profile="software")` names a governance profile. `run()` pins its id on the investigation
  (`software@1`), takes the profile's **seat templates** when `seats=None` (implementer / tester / reviewer / lead;
  quant / risk / lead; researcher / fact_checker / lead; modeller / solver / verifier / lead), and appends the
  profile's **notes** to every seat's preamble (what the record will refuse here, in one paragraph). Roles stay
  three; a profile's seats are workers, reviewers and a lead with domain names and `takes` words.
- **Toolkits** (`hypswarm.toolkits`): named bundles built by a factory from a `ToolContext(record, inv, folder)`.
  hypswarm ships `files` (ADR-006). Anything that executes code or touches a network is the host's to
  `register(name, factory)`; a profile that asks for a toolkit the host has not registered fails loudly rather than
  running without it. `run(..., toolkits=[...], folder=...)` builds them; the profile's list is the default.
- CLI: `hypswarm run --task t.toml --profile software [--seats s.toml] [--folder dir]`; `task.toml` may carry
  `profile = "trading"`; `hypswarm profiles` lists the rosters.

## Consequences

- Tests (`tests/test_profiles.py`): rosters and record predicates mirror HypGraph's; registry build / describe /
  loud failure; a knowledge run with `seats=None` pins `knowledge@1`, issues `sourced` orders to the researcher,
  settles on a cited claim and reports complete; a trading run's costless backtest is refused by the record and no
  edge is ever accepted.
- Adding a domain is: a `Profile` in HypGraph (rules), a roster + notes here, and whatever toolkits the host
  registers. No scheduler change.
- Not yet: per-profile long-horizon task families for the study; a `--profile` for the study harness (A–D stay
  as preregistered; E can take one under a deviation).
