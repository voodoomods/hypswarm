"""
The budget is a hard rule: per run and per order, in model calls and in dollars. The scheduler refuses to issue an
order that can't fit; a worker sees its calls remaining in every reply. Dollars come from the host's meter when it
has one (a proxy ledger), else from the provider's usage fields priced by a table.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


class BudgetExhausted(RuntimeError):
    pass


@dataclass(frozen=True)
class Pricing:
    """$ per million tokens."""
    input: float = 0.0
    cached: float = 0.0
    output: float = 0.0

    def usd(self, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
        return ((input_tokens - cached_tokens) * self.input + cached_tokens * self.cached
                + output_tokens * self.output) / 1_000_000


@dataclass(frozen=True)
class Budget:
    max_calls: int = 150
    max_usd: float = 0.0           # 0 = no dollar cap (calls still cap)
    per_order_calls: int = 40
    warn_at: float = 0.85          # tell the lead to submit at this share of the call budget
    report_calls: int = 8          # calls only the lead's report may use (at most a fifth of max_calls): orders in
                                   # flight used to spend the last call, and the lead never got a report turn (T1)


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0


@dataclass
class Meter:
    """Counts every model call against the budget. ``external`` lets the host supply metered dollars for a label
    (for example from a proxy ledger); when absent, ``pricing`` prices the usage the provider reported.

    Calls in flight count. Workers run in parallel, so a check that looked only at completed calls let every
    worker through when one call was left and billed them all. ``reserve`` claims a call before it is made (the
    check includes reservations), ``add`` consumes the reservation when the call completes, ``release`` gives it
    back when the call failed. Dollars in flight are estimated at the running average cost per call."""
    budget: Budget
    pricing: Pricing | None = None
    external: Callable[[], float] | None = None
    total: Usage = field(default_factory=Usage)
    by_unit: dict[str, Usage] = field(default_factory=dict)
    pending: int = 0                                 # calls reserved and not yet completed
    pending_by_unit: dict[str, int] = field(default_factory=dict)

    def add(self, unit: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> None:
        usd = self.pricing.usd(input_tokens, cached_tokens, output_tokens) if self.pricing else 0.0
        if self.pending_by_unit.get(unit, 0) > 0:    # this call was reserved: the reservation becomes the call
            self.pending -= 1
            self.pending_by_unit[unit] -= 1
        for u in (self.total, self.by_unit.setdefault(unit, Usage())):
            u.calls += 1
            u.input_tokens += input_tokens
            u.cached_tokens += cached_tokens
            u.output_tokens += output_tokens
            u.usd += usd

    @property
    def usd(self) -> float:
        return self.external() if self.external else self.total.usd

    def calls_left(self) -> int:
        return max(0, self.budget.max_calls - self.total.calls - self.pending)

    def _avg_usd(self) -> float:
        return self.usd / self.total.calls if self.total.calls else 0.0

    def check(self, unit: str = "") -> None:
        """Raise when the next call would break the budget (run or order), counting calls in flight. The last
        ``report_calls`` are the report's: any other unit stops short of them."""
        held = 0 if unit == "report" else min(self.budget.report_calls, self.budget.max_calls // 5)
        if self.total.calls + self.pending >= self.budget.max_calls - held:
            raise BudgetExhausted(f"{self.budget.max_calls} model calls"
                                  + (f" ({held} held for the report)" if held else ""))
        if self.budget.max_usd and self.usd + self.pending * self._avg_usd() >= self.budget.max_usd:
            raise BudgetExhausted(f"${self.budget.max_usd:.2f}")
        if unit and self.by_unit.get(unit, Usage()).calls + self.pending_by_unit.get(unit, 0) \
                >= self.budget.per_order_calls:
            raise BudgetExhausted(f"{self.budget.per_order_calls} calls on {unit}")

    def reserve(self, unit: str = "") -> None:
        """Claim the next call for ``unit`` (raises BudgetExhausted if it can't fit). Pair with ``add`` on success
        or ``release`` on failure. Atomic under asyncio: no await between the check and the claim."""
        self.check(unit)
        self.pending += 1
        self.pending_by_unit[unit] = self.pending_by_unit.get(unit, 0) + 1

    def release(self, unit: str = "") -> None:
        """Give back a reservation whose call never completed."""
        if self.pending_by_unit.get(unit, 0) > 0:
            self.pending -= 1
            self.pending_by_unit[unit] -= 1

    def orders_spent(self) -> bool:
        """Only the report's calls (or none) are left: no order can make another call."""
        try:
            self.check("")
        except BudgetExhausted:
            return True
        return False

    def warn(self) -> bool:
        return self.total.calls >= self.budget.warn_at * self.budget.max_calls

    def summary(self) -> dict[str, object]:
        return {"calls": self.total.calls, "input_tokens": self.total.input_tokens,
                "cached_tokens": self.total.cached_tokens, "output_tokens": self.total.output_tokens,
                "usd": round(self.usd, 6), "by_unit": {k: v.calls for k, v in self.by_unit.items()}}
