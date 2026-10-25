"""
The record client: everything hypswarm needs from a HypGraph record, behind one small surface so the in-process
Graph (alpha) and a record server over HTTP / MCP (later) are interchangeable. Workers never touch the SQLite
file directly in server mode; here they share one Graph, which serialises writes itself.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from hypgraph import Graph, GraphError, Policy

from .seats import Seat

INSTRUMENT = "instrument"
HARNESS = "harness"


class Record(Protocol):
    def briefing(self, inv: str, *, roster: list[dict[str, str]] | None, since_seq: int) -> dict[str, Any]: ...
    def question_board(self, inv: str) -> list[dict[str, Any]]: ...
    def orders(self, inv: str, status: str = "") -> list[dict[str, Any]]: ...
    def issue_work(self, **kw: Any) -> dict[str, Any]: ...
    def order_text(self, order: str) -> str: ...
    def check_work(self, order: str, text: str = "") -> dict[str, Any]: ...
    def settle(self, *, author: str, inv: str) -> list[dict[str, Any]]: ...
    def rework(self, *, author: str, order: str, missing: str, done_when: list[Any] | None = None) -> dict[str, Any]: ...
    def cancel_work(self, *, author: str, order: str, why: str) -> dict[str, Any]: ...
    def cancel_moot(self, *, author: str, inv: str) -> list[dict[str, Any]]: ...
    def return_work(self, *, author: str, order: str, note: str = "") -> dict[str, Any]: ...
    def create(self, **kw: Any) -> dict[str, Any]: ...
    def review(self, **kw: Any) -> dict[str, Any]: ...
    def get(self, nid: str) -> dict[str, Any]: ...
    def resolve(self, ref: str, inv: str = "") -> str: ...
    def search(self, text: str = "", type: str = "", inv: str = "", limit: int = 50) -> list[dict[str, Any]]: ...
    def report(self, inv: str) -> dict[str, Any]: ...
    def check_text(self, text: str, inv: str = "") -> dict[str, Any]: ...
    def next_experiments(self, inv: str, limit: int = 10) -> dict[str, Any]: ...


class LocalRecord:
    """A HypGraph record in this process. Policy: the reviewer seats' verdicts count; ``instrument`` files
    lab-recorded runs; the harness itself writes as ``harness`` — an ordinary author that owns the orders it
    issues, held to the same rules as everyone (it writes no claims)."""

    def __init__(self, path: str | Path | None, seats: Sequence[Seat], *, spend: Any = None,
                 max_creates_per_minute: int = 600):
        reviewers = frozenset(s.name for s in seats if s.role == "reviewer")
        self.policy = Policy(reviewers=reviewers, instrument=INSTRUMENT, operator="operator",
                             max_creates_per_minute=max_creates_per_minute)
        self.g = Graph(str(path) if path else None, policy=self.policy, spend=spend)

    # the surface
    def __getattr__(self, name: str) -> Any:
        return getattr(self.g, name)

    def close(self) -> None:
        self.g.close()

    # seeding a task
    def start(self, title: str, objective: str, questions: Iterable[tuple[str, str]], *, success: str = "",
              strict: bool = True, files: Mapping[str, bytes] | None = None) -> str:
        inv: str = self.g.create(author=HARNESS, type="investigation", fields={
            "title": title[:200], "objective": objective, "success_criteria": success or
            "Every question answered from the evidence, with the evidence in the record.", "strict_claims": strict})["id"]
        for code, text in questions:
            self.g.create(author=HARNESS, type="question", inv=inv, code=code, fields={"text": text})
        for name, data in (files or {}).items():
            self.g.create(author=HARNESS, type="artifact", inv=inv, fields={
                "sha256": hashlib.sha256(data).hexdigest(), "path": name, "size": len(data),
                "format": Path(name).suffix.lstrip(".")})
        return inv

    def file_run(self, inv: str, config: dict[str, Any]) -> str:
        """The run's own provenance: hypswarm version, seats and models, budget, prompt hashes."""
        rid: str = self.g.create(author=HARNESS, type="run", inv=inv, fields={
            "kind": "agent", "name": "hypswarm run", "state": "running", "config": config})["id"]
        return rid

    def finish_run(self, rid: str, state: str, note: str = "") -> None:
        try:
            self.g.revise(author=HARNESS, node=rid, reason="the run ended", fields={"state": state, "note": note[:2000]})
        except GraphError:
            pass


__all__ = ["HARNESS", "INSTRUMENT", "LocalRecord", "Record"]
