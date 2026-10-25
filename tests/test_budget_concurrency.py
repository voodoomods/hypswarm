"""The budget is a hard rule under concurrency: with N workers in flight and one call left, exactly one call is
made. Before reservations, every worker passed the check and every one was billed."""
import asyncio

import pytest

from hypswarm import Budget, Seat, Task, run
from hypswarm.budget import BudgetExhausted, Meter
from hypswarm.messages import Reply, ToolCall


class YieldingStub:
    """Like StubModel, but the call yields to the event loop between the budget check and the add — as a real
    provider does for seconds. Every call asks for `find`, so a worker never returns and keeps calling."""

    def __init__(self) -> None:
        self.name = "yielding-stub"
        self.calls = 0

    async def complete(self, messages, tools, *, temperature=None, unit=""):
        self.calls += 1
        await asyncio.sleep(0.01)
        return Reply(content="", tool_calls=(ToolCall(f"c{self.calls}", "find", {"text": "accuracy"}),),
                     input_tokens=100, cached_tokens=0, output_tokens=10)


TASK = Task(title="budget race", mission="Count things.",
            questions=[(f"Q{i}", f"How many of kind {i}?") for i in range(1, 6)])


def test_five_parallel_workers_three_calls_make_exactly_three():
    model = YieldingStub()
    seats = [Seat(f"w{i}", "worker") for i in range(1, 6)]
    res = asyncio.run(run(TASK, seats, model, record=None, budget=Budget(max_calls=3, per_order_calls=40)))
    assert model.calls == 3, f"{model.calls} calls were made against a cap of 3"
    assert res.usage["calls"] == 3
    assert res.stopped.startswith("budget")


def test_reserve_add_release_bookkeeping():
    m = Meter(Budget(max_calls=2, per_order_calls=1))
    m.reserve("O1")
    assert m.pending == 1 and m.calls_left() == 1
    with pytest.raises(BudgetExhausted):          # the per-order cap counts the reservation
        m.reserve("O1")
    m.reserve("O2")
    with pytest.raises(BudgetExhausted):          # the run cap counts both reservations
        m.reserve("O3")
    m.release("O2")
    m.add("O1", 10, 0, 5)                         # consumes O1's reservation
    assert m.pending == 0 and m.total.calls == 1 and m.calls_left() == 1
    m.add("O9", 10, 0, 5)                         # an unreserved add still counts (legacy callers)
    assert m.total.calls == 2 and m.pending == 0


def test_dollar_cap_counts_calls_in_flight():
    from hypswarm.budget import Pricing
    m = Meter(Budget(max_calls=100, max_usd=0.0003), Pricing(input=1.0, output=1.0))   # $1 per million tokens
    m.add("a", 100, 0, 0)                          # $0.0001 so far, average $0.0001 a call
    m.reserve("b")
    m.reserve("c")                                 # $0.0001 + 2 × $0.0001 = the cap
    with pytest.raises(BudgetExhausted):
        m.reserve("d")
