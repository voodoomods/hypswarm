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
    (for example from a proxy ledger); when absent, ``pricing`` prices the usage the provider reported."""
    budget: Budget
    pricing: Pricing | None = None
    external: Callable[[], float] | None = None
    total: Usage = field(default_factory=Usage)
    by_unit: dict[str, Usage] = field(default_factory=dict)

    def add(self, unit: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> None:
        usd = self.pricing.usd(input_tokens, cached_tokens, output_tokens) if self.pricing else 0.0
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
        return max(0, self.budget.max_calls - self.total.calls)

    def check(self, unit: str = "") -> None:
        """Raise when the next call would break the budget (run or order)."""
        if self.total.calls >= self.budget.max_calls:
            raise BudgetExhausted(f"{self.budget.max_calls} model calls")
        if self.budget.max_usd and self.usd >= self.budget.max_usd:
            raise BudgetExhausted(f"${self.budget.max_usd:.2f}")
        if unit and self.by_unit.get(unit, Usage()).calls >= self.budget.per_order_calls:
            raise BudgetExhausted(f"{self.budget.per_order_calls} calls on {unit}")

    def warn(self) -> bool:
        return self.total.calls >= self.budget.warn_at * self.budget.max_calls

    def summary(self) -> dict[str, object]:
        return {"calls": self.total.calls, "input_tokens": self.total.input_tokens,
                "cached_tokens": self.total.cached_tokens, "output_tokens": self.total.output_tokens,
                "usd": round(self.usd, 6), "by_unit": {k: v.calls for k, v in self.by_unit.items()}}
