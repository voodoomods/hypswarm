"""
The record over HTTP: workers talk to ``hypgraph serve --writable`` instead of sharing one Graph in a process.
One record server, many stateless workers — on other processes or machines — and the record is still the only
shared state. Writes are bound to a bearer token when the server was started with ``--token``: pass it as
``token=``. The swarm's own token must cover the harness and every seat it runs (``SECRET=harness,analyst,…``),
because this one client writes as each of them; an outside seat gets a token bound to its own name only. A server
without tokens authenticates nobody: keep it on localhost or behind your own auth (``headers=``).

Same surface as LocalRecord (the ``Record`` protocol plus start / file_run / finish_run), so ``run(...,
record=HttpRecord(url))`` is the only change.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import httpx
from hypgraph import GraphError

from .record import HARNESS


class AuthError(GraphError):  # type: ignore[misc]  # hypgraph ships no py.typed yet: GraphError is Any here
    """The record server refused the caller's identity (no token, an unknown token, or an author the token isn't
    bound to) — not a refusal of the write's content."""


class HttpRecord:
    def __init__(self, base_url: str, *, headers: Mapping[str, str] | None = None, timeout_s: float = 30.0,
                 client: httpx.Client | None = None, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.path = self.base_url                       # what the run's provenance and the MCP hint show
        hdrs = dict(headers or {})
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        self._c = client or httpx.Client(base_url=self.base_url, headers=hdrs,
                                         timeout=httpx.Timeout(timeout_s, connect=10.0))

    def close(self) -> None:
        self._c.close()

    # ── transport ────────────────────────────────────────────
    @staticmethod
    def _raise(r: httpx.Response) -> None:
        if r.status_code < 400:
            return
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        if r.status_code == 404:
            raise KeyError(detail)
        if r.status_code == 401 or (r.status_code == 403 and "token" in str(detail)):
            raise AuthError(f"{detail}")
        raise GraphError(f"{detail}")

    def _get(self, path: str, **params: Any) -> Any:
        r = self._c.get(f"/api/graph/{path}", params={k: v for k, v in params.items() if v not in (None, "")})
        self._raise(r)
        return r.json()

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        r = self._c.post(f"/api/graph/{path}", json=body)
        self._raise(r)
        return r.json()

    def _write(self, op: str, author: str, **kw: Any) -> Any:
        return self._post("write", {"op": op, "author": author, **{k: v for k, v in kw.items() if v is not None}})

    # ── the Record surface ───────────────────────────────────
    def briefing(self, inv: str, *, roster: list[dict[str, str]] | None = None, since_seq: int = 0,
                 budget_usd: float = 0) -> dict[str, Any]:
        out: dict[str, Any] = self._post("briefing", {"inv": inv, "roster": roster, "since_seq": since_seq})
        return out

    def question_board(self, inv: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = self._get("board", inv=inv)["board"]
        return out

    def orders(self, inv: str, status: str = "") -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = self._get("orders", inv=inv, status=status)["orders"]
        return out

    def issue_work(self, **kw: Any) -> dict[str, Any]:
        author = str(kw.pop("author"))
        out: dict[str, Any] = self._write("issue_work", author, **kw)
        return out

    def order_text(self, order: str) -> str:
        return str(self._get(f"order/{order}")["text"])

    def check_work(self, order: str, text: str = "") -> dict[str, Any]:
        out: dict[str, Any] = self._post("check_work", {"order": order, "text": text})
        return out

    def settle(self, *, author: str, inv: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = self._write("settle", author, inv=inv)
        return out

    def rework(self, *, author: str, order: str, missing: str, done_when: list[Any] | None = None) -> dict[str, Any]:
        out: dict[str, Any] = self._write("rework", author, order=order, missing=missing, done_when=done_when)
        return out

    def cancel_work(self, *, author: str, order: str, why: str) -> dict[str, Any]:
        out: dict[str, Any] = self._write("cancel_work", author, order=order, why=why)
        return out

    def cancel_moot(self, *, author: str, inv: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = self._write("cancel_moot", author, inv=inv)
        return out

    def return_work(self, *, author: str, order: str, note: str = "") -> dict[str, Any]:
        out: dict[str, Any] = self._write("return_work", author, order=order, note=note)
        return out

    def create(self, **kw: Any) -> dict[str, Any]:
        author = str(kw.pop("author"))
        out: dict[str, Any] = self._write("create", author, **kw)
        return out

    def revise(self, **kw: Any) -> dict[str, Any]:
        author = str(kw.pop("author"))
        out: dict[str, Any] = self._write("revise", author, **kw)
        return out

    def review(self, **kw: Any) -> dict[str, Any]:
        author = str(kw.pop("author"))
        out: dict[str, Any] = self._write("review", author, **kw)
        return out

    def withdraw(self, **kw: Any) -> dict[str, Any]:
        author = str(kw.pop("author"))
        out: dict[str, Any] = self._write("withdraw", author, **kw)
        return out

    def get(self, nid: str, history: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = self._get(f"node/{nid}", history="1" if history else "")
        return out

    def resolve(self, ref: str, inv: str = "") -> str:
        return str(self._get("resolve", ref=ref, inv=inv)["id"])

    def search(self, text: str = "", type: str = "", inv: str = "", limit: int = 50) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = self._get("search", text=text, type=type, inv=inv, limit=limit)["results"]
        return out

    def report(self, inv: str) -> dict[str, Any]:
        out: dict[str, Any] = self._get("report", inv=inv)
        return out

    def check_text(self, text: str, inv: str = "") -> dict[str, Any]:
        out: dict[str, Any] = self._post("check", {"text": text, "inv": inv})
        return out

    def next_experiments(self, inv: str, limit: int = 10) -> dict[str, Any]:
        out: dict[str, Any] = self._get("next", inv=inv, limit=limit)
        return out

    def investigations(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = self._get("investigations")["investigations"]
        return out

    # ── seeding a task (same as LocalRecord) ─────────────────
    def start(self, title: str, objective: str, questions: Iterable[tuple[str, str]], *, success: str = "",
              strict: bool = True, files: Mapping[str, bytes] | None = None,
              reviewers: Iterable[str] = ()) -> str:
        """Seed the task. ``reviewers`` go on the investigation itself, so their verdicts count wherever the record
        is opened — a served record's process knows nothing of the seats."""
        inv = str(self.create(author=HARNESS, type="investigation", fields={
            "title": title[:200], "objective": objective, "success_criteria": success or
            "Every question answered from the evidence, with the evidence in the record.", "strict_claims": strict,
            "reviewers": sorted(set(reviewers))})["id"])
        for code, text in questions:
            self.create(author=HARNESS, type="question", inv=inv, code=code, fields={"text": text})
        for name, data in (files or {}).items():
            self.create(author=HARNESS, type="artifact", inv=inv, fields={
                "sha256": hashlib.sha256(data).hexdigest(), "path": name, "size": len(data),
                "format": Path(name).suffix.lstrip(".")})
        return inv

    def file_run(self, inv: str, config: dict[str, Any]) -> str:
        return str(self.create(author=HARNESS, type="run", inv=inv, fields={
            "kind": "agent", "name": "hypswarm run", "state": "running", "config": config})["id"])

    def finish_run(self, rid: str, state: str, note: str = "") -> None:
        try:
            self.revise(author=HARNESS, node=rid, reason="the run ended", fields={"state": state, "note": note[:2000]})
        except GraphError:
            pass
