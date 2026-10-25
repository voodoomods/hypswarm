"""
Seats: declared capabilities bound to an author name in the record. Prompts stay short; the work order carries
the task. A solo scientist is one worker seat; a swarm is several, pulling in parallel under leases.

    worker      takes orders from the board; writes runs, results, claims; returns
    reviewer    takes review orders; named as a reviewer in the record's policy, so its verdicts count
    lead        called only at exceptions (an order stuck after two reworks, a contested claim, an empty frontier
                with questions open) and for the report's interpretation
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ROLES = ("worker", "reviewer", "lead")
_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")
RESERVED = {"lab", "operator", "importer", "system", "harness", "instrument"}


@dataclass(frozen=True)
class Seat:
    name: str                      # the author name in the record (lower-case, ≤ 40 characters)
    role: str = "worker"           # worker | reviewer | lead
    model: str = ""                # provider model id; empty = the run's default
    takes: tuple[str, ...] = ()    # words naming the work it fits (matched against questions and targets)
    about: str = ""                # one line for the seat's prompt: who it is and what it is careful about
    temperature: float | None = None
    max_turns: int = 14            # per order
    tools: tuple[str, ...] = ("*",)  # names of the host's data tools it may use ("*" = all)
    extra: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise ValueError(f"seat name {self.name!r}: lower-case letters, digits, - or _, 2–40 characters")
        if self.name in RESERVED:
            raise ValueError(f"seat name {self.name!r} is reserved")
        if self.role not in ROLES:
            raise ValueError(f"role must be one of {', '.join(ROLES)}")

    def may_use(self, tool_name: str) -> bool:
        return "*" in self.tools or tool_name in self.tools

    def prompt(self) -> str:
        who = self.about or {
            "worker": "You do the work an order asks for, from the files, and write what you find into the record.",
            "reviewer": "You check a teammate's claim against the files and the record, and record a verdict.",
            "lead": "You judge exceptions the record can't settle, and you write the interpretation under the facts.",
        }[self.role]
        return (f"You are {self.name} ({self.role}). {who}\n"
                "You coordinate through the record, not through conversation: your deliverable is what you write "
                "into it (runs, results, claims, reviews). Claims are checked as they are written; a refused claim "
                "tells you exactly what to fix, and the honest version is the one to write. Every record reply "
                "tells you whether your order is done: when it says return_work now, return.")


def fit(seat: Seat, text: str, target_type: str) -> float:
    """How well a seat fits a piece of work: its declared words against the work's words, plus its role."""
    words = set(re.findall(r"[a-z]{4,}", text.lower()))
    hits = sum(1 for t in seat.takes if t.lower() in words or t.lower() == target_type)
    return hits + (0.5 if target_type in seat.takes else 0)
