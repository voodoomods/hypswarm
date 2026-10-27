"""A seat that returns at once at no cost never keeps a run alive. A crashing agent's reservation is released, and once
only the report's calls are left every seat returns without a call; each return was reworked or cancelled for free,
and once the record's clock moved past a second ("no live claim since the order was issued") a fresh order was issued
and dispatched again, forever. The real clock rarely moves inside these runs on a fast machine, so the hang showed on
a slower CI runner only; the record's clock is moved here on every write."""
from __future__ import annotations

import asyncio
import itertools
from datetime import UTC, datetime, timedelta

import hypgraph.graph as hg_graph
import pytest

from hypswarm import Budget, Seat, run
from hypswarm.agents import AgentOrder, AgentOutcome
from hypswarm.providers.stub import StubModel

from .test_alpha import TASK, lead_script, reviewer_script


@pytest.fixture
def moving_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    tick = itertools.count()
    base = datetime(2026, 10, 27, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(hg_graph, "now", lambda: (base + timedelta(seconds=next(tick))).isoformat(timespec="seconds"))


async def boom(order: AgentOrder) -> AgentOutcome:
    raise RuntimeError("framework exploded")


async def idle(order: AgentOrder) -> AgentOutcome:
    return AgentOutcome(note="nothing to report", calls=1)


def _run(seats: list[Seat], **budget: int):
    models = {"reviewer": StubModel(reviewer_script), "lead": StubModel(lead_script)}
    return asyncio.run(asyncio.wait_for(run(TASK, seats, models, record=None, budget=Budget(**budget)), 30))


@pytest.mark.parametrize("lead", [True, False])
def test_a_seat_that_always_crashes_is_benched(moving_clock: None, lead: bool) -> None:
    seats = [Seat("analyst", "worker", agent=boom), Seat("critic", "reviewer")] + ([Seat("lead", "lead")] if lead else [])
    r = _run(seats, max_calls=20, per_order_calls=4)
    s = r.scheduler
    assert s.benched == ["analyst"] and r.stopped == "stuck"
    assert sum(1 for w in s.workers if w.seat == "analyst") == 3
    assert any(e["kind"] == "benched" and "framework exploded" in e["why"] for e in s.events)


def test_nothing_is_dispatched_once_only_the_reports_calls_are_left(moving_clock: None) -> None:
    seats = [Seat("analyst", "worker", agent=idle), Seat("critic", "reviewer"), Seat("lead", "lead")]
    r = _run(seats, max_calls=20, per_order_calls=4)
    assert r.stopped.startswith("budget")
    assert not any(str(w.stopped).startswith("budget") for w in r.scheduler.workers)   # none started past it
    assert r.usage["calls"] <= 20


def test_one_crash_is_not_a_bench(moving_clock: None) -> None:
    n = {"calls": 0}

    async def flaky(order: AgentOrder) -> AgentOutcome:
        n["calls"] += 1
        if n["calls"] % 2:
            raise RuntimeError("transient")
        return AgentOutcome(note="nothing to report", calls=1)
    seats = [Seat("analyst", "worker", agent=flaky), Seat("critic", "reviewer"), Seat("lead", "lead")]
    r = _run(seats, max_calls=20, per_order_calls=4)
    assert r.scheduler.benched == [] and n["calls"] > 3
