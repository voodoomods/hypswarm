"""
The scheduler makes no model calls. It issues orders from the question board, settles the ones whose predicates
are met, reworks the rest (twice), cancels what became moot, and brings in the lead seat only at exceptions and
for the report. Workers run in parallel as asyncio tasks; the record's leases keep them off each other's work.
Every scheduler action is already an event in the record (orders are task nodes, acceptance a decision), so the
run's audit trail is the record itself.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from hypgraph import GraphError

from .budget import BudgetExhausted, Meter
from .messages import Message, Tool
from .providers.base import ChatModel
from .record import HARNESS, LocalRecord
from .seats import Seat, fit
from .tools import lead_tools
from .worker import WorkerResult, await_external, run_order

log = logging.getLogger("hypswarm.scheduler")


@dataclass
class SchedulerResult:
    stopped: str = ""                       # settled | budget | stuck | cancelled
    rounds: int = 0
    orders_issued: int = 0
    reworks: int = 0
    escalations: int = 0
    lead_calls: int = 0
    report: str = ""
    report_accepted: bool = False
    workers: list[WorkerResult] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    lead_log: list[dict[str, Any]] = field(default_factory=list)   # one row per lead model call
    notices: list[dict[str, Any]] = field(default_factory=list)


class Scheduler:
    def __init__(self, record: LocalRecord, inv: str, seats: Sequence[Seat], model_for: Callable[[Seat], ChatModel],
                 meter: Meter, *, data_tools: Sequence[Tool] = (), preamble: str = "", max_reworks: int = 2,
                 lease_minutes: int = 240, lead_turns: int = 6,
                 on_return: Callable[[Scheduler, int], None] | None = None, external_poll_s: float = 1.0,
                 external_timeout_s: float | None = None):
        self.r, self.inv, self.seats = record, inv, list(seats)
        self.model_for, self.meter = model_for, meter
        self.data_tools, self.preamble = list(data_tools), preamble
        self.max_reworks, self.lease_minutes, self.lead_turns = max_reworks, lease_minutes, lead_turns
        self.workers = [s for s in seats if s.role == "worker"]
        self.reviewers = [s for s in seats if s.role == "reviewer"]
        self.lead = next((s for s in seats if s.role == "lead"), None)
        self.roster = [{"name": s.name, "takes": ", ".join(s.takes) or s.role} for s in seats]
        self.busy: dict[str, str] = {}                      # seat → order id
        self.inflight: dict[asyncio.Task[WorkerResult], tuple[Seat, str]] = {}
        self.chain: dict[str, str] = {}                     # order → root order (rework chains)
        self.reworked: dict[str, int] = {}                  # root → reworks so far
        self.res = SchedulerResult()
        self._stop = False
        self._pending_lead: list[tuple[dict[str, Any], str]] = []
        self.on_return = on_return                          # host hook after each worker return (count so far)
        self.external_poll_s = external_poll_s
        self.external_timeout_s = external_timeout_s if external_timeout_s is not None else lease_minutes * 60.0
        self.returns = 0
        self.notices: list[str] = []

    # ── notices: something the world tells the team mid-run ──
    def notify(self, text: str, *, stale: Sequence[str] = (), add_files: dict[str, bytes] | None = None) -> None:
        """A notice from outside (a data file declared corrupt, a corrected file): the stale artifacts are
        withdrawn in the record with the notice as the reason, new files are registered, and the text reaches every
        order issued from now on and the lead's prompts. Orders already in flight learn of it through the record
        (their premises fall) and through cancel_moot."""
        import hashlib
        for name in stale:
            for a in self.r.search(name, type="artifact", inv=self.inv):
                if a.get("title", "").strip() == name:
                    try:
                        self.r.withdraw(author=HARNESS, node=a["id"], why=text[:900])
                    except GraphError as e:
                        self._ev("notice_withdraw_failed", artifact=name, why=str(e)[:120])
        for name, data in (add_files or {}).items():
            self.r.create(author=HARNESS, type="artifact", inv=self.inv, fields={
                "sha256": hashlib.sha256(data).hexdigest(), "path": name, "size": len(data),
                "format": name.rsplit(".", 1)[-1] if "." in name else ""})
        self.notices.append(text)
        self.res.notices.append({"t": round(time.time(), 3), "text": text, "stale": list(stale),
                                 "added": sorted(add_files or {}), "after_calls": self.meter.total.calls})
        self._ev("notice", stale=list(stale), added=sorted(add_files or {}))

    def _preamble(self) -> str:
        if not self.notices:
            return self.preamble
        return self.preamble + "\n\nNOTICES (read before anything else)\n" + "\n".join(f"- {n}" for n in self.notices)

    # ── events ───────────────────────────────────────────────
    def _ev(self, kind: str, **kw: Any) -> None:
        e = {"t": round(time.time(), 3), "kind": kind, **kw}
        self.res.events.append(e)
        log.info("%s %s", kind, kw)

    def stop(self) -> None:
        self._stop = True

    # ── dispatch ─────────────────────────────────────────────
    def _idle(self, pool: Sequence[Seat]) -> list[Seat]:
        return [s for s in pool if s.name not in self.busy]

    def _pick(self, pool: Sequence[Seat], text: str, ttype: str) -> Seat | None:
        idle = self._idle(pool)
        return max(idle, key=lambda s: (fit(s, text, ttype), -self.seats.index(s))) if idle else None

    def _dispatch(self, seat: Seat, order: str) -> None:
        self.busy[seat.name] = order
        if seat.external:
            task = asyncio.create_task(await_external(seat, self.r, self.inv, order, timeout_s=self.external_timeout_s,
                                                      poll_s=self.external_poll_s))
        else:
            task = asyncio.create_task(run_order(seat, self.model_for(seat), self.r, self.inv, order, meter=self.meter,
                                                 data_tools=self.data_tools, preamble=self._preamble()))
        self.inflight[task] = (seat, order)
        self._ev("dispatch", seat=seat.name, order=self.r.get(order)["code"], external=seat.external)

    def _issue(self, seat: Seat, target: str, objective: str, done_when: list[Any] | None = None) -> bool:
        try:
            o = self.r.issue_work(author=HARNESS, inv=self.inv, target=target, assignee=seat.name, role=seat.role,
                                  objective=objective, done_when=done_when, lease_minutes=self.lease_minutes)
        except GraphError as e:
            self._ev("issue_refused", seat=seat.name, target=target, why=str(e)[:200])
            return False
        self.res.orders_issued += 1
        self.chain[o["order"]] = o["order"]
        self._dispatch(seat, o["order"])
        return True

    # ── one round ────────────────────────────────────────────
    def _settle_and_rework(self) -> None:
        moot = self.r.cancel_moot(author=HARNESS, inv=self.inv)
        for m in moot:
            self._ev("cancel_moot", order=m["order"], because=m["because"])
        for d in self.r.settle(author=HARNESS, inv=self.inv):
            self._ev("settled", order=d["order"], decision=d["decision"])
        for o in self.r.orders(self.inv, status="returned"):
            chk = self.r.check_work(o["id"])
            if chk["all_met"]:
                continue
            root = self.chain.get(o["id"], o["id"])
            seat = next((s for s in self.seats if s.name == o["assignee"]), None)
            missing = "; ".join(x["why"] or x["p"] for x in chk["predicates"] if not x["met"])
            if seat and self.reworked.get(root, 0) < self.max_reworks and seat.name not in self.busy:
                try:
                    rw = self.r.rework(author=HARNESS, order=o["id"], missing=missing[:1000])
                except GraphError as e:
                    self._ev("rework_refused", order=o["code"], why=str(e)[:200])
                    continue
                self.reworked[root] = self.reworked.get(root, 0) + 1
                self.res.reworks += 1
                self.chain[rw["order"]] = root
                self._ev("rework", order=o["code"], as_=rw["code"], missing=missing[:200])
                self._dispatch(seat, rw["order"])
            elif seat and seat.name in self.busy:
                continue                                    # decide once the seat is free
            else:
                self._escalate(o, missing)

    def _escalate(self, o: dict[str, Any], missing: str) -> None:
        """The lead judges an order the record couldn't settle; without a lead, it is cancelled with the reason."""
        self.res.escalations += 1
        if not self.lead:
            self.r.cancel_work(author=HARNESS, order=o["id"], why=f"stuck after {self.max_reworks} reworks: {missing}"[:900])
            self._ev("cancelled", order=o["code"], why="no lead seat")
            return
        self._ev("escalate", order=o["code"], missing=missing[:200])
        self._pending_lead.append((o, missing))

    def _assign(self) -> None:
        if self.meter.warn():
            return                                          # drain; the report is next
        board = self.r.question_board(self.inv)
        busy_targets = {o["target_id"] for o in self.r.orders(self.inv) if o["status"] in ("open", "overdue", "returned")}
        for q in board:
            if q["status"] == "open" and q["id"] not in busy_targets:
                seat = self._pick(self.workers, q["text"], "question")
                if seat and self._issue(seat, q["id"], f"Answer {q['code']}: {q['text']}"):
                    busy_targets.add(q["id"])
            elif q["status"] == "answered" and self.reviewers:
                claim = self.r.resolve(q["answers"][-1], self.inv)
                if claim in busy_targets:
                    continue
                author = self.r.get(claim)["by"]
                pool = [s for s in self.reviewers if s.name != author]
                seat = self._pick(pool, q["text"], "claim")
                if seat and self._issue(seat, claim, f"Review {q['answers'][-1]}, which answers {q['code']}: check its "
                                                     "numbers and reasoning against the files and the record.",
                                        [{"p": "reviewed"}]):
                    busy_targets.add(claim)
        try:
            nx = self.r.next_experiments(self.inv, limit=10)
        except (GraphError, KeyError):
            nx = {"ranked": []}
        for x in nx["ranked"]:
            xid = x["experiment"]["id"]
            if x["duplicate"] or x["lease"] or xid in busy_targets:
                continue
            seat = self._pick(self.workers, x["experiment"]["title"], "experiment")
            if seat and self._issue(seat, xid, f"Run {x['experiment']['code']}: {x['experiment']['title']}"):
                busy_targets.add(xid)

    def _done(self) -> str:
        board = self.r.question_board(self.inv)
        if board and all(q["status"] in ("settled", "contested") for q in board) and not self.inflight:
            return "settled"
        if not self.inflight and not self._pending_lead:
            open_orders = [o for o in self.r.orders(self.inv) if o["status"] in ("open", "overdue", "returned")]
            if not open_orders:
                return "stuck" if any(q["status"] in ("open", "answered", "in progress") for q in board) else "settled"
        return ""

    # ── the loop ─────────────────────────────────────────────
    async def run(self) -> SchedulerResult:
        while not self._stop:
            self.res.rounds += 1
            try:
                self._settle_and_rework()
                while self._pending_lead:
                    o, missing = self._pending_lead.pop(0)
                    await self._lead_judges(o, missing)
                self._assign()
            except BudgetExhausted as e:
                self.res.stopped = f"budget: {e}"
                break
            why = self._done()
            if (why == "stuck" or (not why and not self.inflight)) and self.meter.warn():
                why = "budget: warning threshold"           # nothing more is issued past the threshold
            if why or not self.inflight:
                self.res.stopped = why or "stuck"
                break
            done, _ = await asyncio.wait(set(self.inflight), return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                seat, order = self.inflight.pop(t)
                self.busy.pop(seat.name, None)
                try:
                    wr = t.result()
                except Exception as e:  # noqa: BLE001
                    wr = WorkerResult(order=order, code=self.r.get(order)["code"], seat=seat.name, stopped=f"error: {e}")
                self.res.workers.append(wr)
                self._ev("returned", seat=seat.name, order=wr.code, calls=wr.calls, returned=wr.returned,
                         by_record=wr.returned_by_record, stopped=wr.stopped)
                self.returns += 1
                if self.on_return:
                    try:
                        self.on_return(self, self.returns)
                    except Exception as e:  # noqa: BLE001 — a host hook never ends the run
                        self._ev("hook_error", why=str(e)[:200])
        for t in list(self.inflight):                       # drain anything still running (budget stop)
            t.cancel()
        self.res.report, self.res.report_accepted = await self._report()
        return self.res

    # ── the lead ─────────────────────────────────────────────
    async def _lead_turns(self, user: str, tools: list[Tool], unit: str, turns: int) -> None:
        assert self.lead
        model = self.model_for(self.lead)
        messages = [Message("system", self.lead.prompt() + "\n\n" + self._preamble()), Message("user", user)]
        by = {t.name: t for t in tools}
        for _ in range(turns):
            try:
                self.meter.check(unit)
            except BudgetExhausted:
                return
            t0 = time.time()
            reply = await model.complete(messages, tools, temperature=self.lead.temperature, unit=unit)
            self.meter.add(unit, reply.input_tokens, reply.cached_tokens, reply.output_tokens)
            self.res.lead_calls += 1
            self.res.lead_log.append({"t": round(t0, 3), "s": round(time.time() - t0, 3), "unit": unit,
                                      "agent": self.lead.name, "in": reply.input_tokens,
                                      "cached": reply.cached_tokens, "out": reply.output_tokens})
            messages.append(reply.as_message())
            if not reply.tool_calls:
                return
            for tc in reply.tool_calls:
                tool = by.get(tc.name)
                out = await tool.call(tc.args) if tool else f"error: no tool {tc.name!r}"
                messages.append(Message("tool", out[:12000], tool_call_id=tc.id))
                if tc.name == "submit_report" and out == "report accepted":
                    return

    async def _lead_judges(self, o: dict[str, Any], missing: str) -> None:
        assert self.lead
        box: dict[str, Any] = {}
        tools = [t for t in lead_tools(self.r, self.lead, self.inv, self.meter, report_box=box, roster=self.roster,
                                       order_author=HARNESS) if t.name != "submit_report"]
        user = (f"EXCEPTION: order {o['code']} ({o['assignee']}, on {o['target']}) came back without its predicates "
                f"met after {self.max_reworks} reworks. Missing: {missing}\nNote from the worker: {o['returned_note'][:400]}\n"
                "Decide: rework it with changed predicates (rework with done_when), cancel it (cancel_work), or add "
                "what is missing to the plan (add). Call briefing first if you need the board.")
        await self._lead_turns(user, tools, f"{o['code']}:lead", self.lead_turns)
        st = {x["id"]: x["status"] for x in self.r.orders(self.inv)}
        if st.get(o["id"]) == "returned":                   # the lead left it: cancel, so the run can end
            self.r.cancel_work(author=HARNESS, order=o["id"], why=f"the lead left it undecided; missing: {missing}"[:900])
            self._ev("cancelled", order=o["code"], why="undecided by the lead")
        for rw in self.r.orders(self.inv, status="open"):   # a rework the lead issued: dispatch it
            seat = next((s for s in self.seats if s.name == rw["assignee"]), None)
            if seat and seat.name not in self.busy and not any(v == rw["id"] for v in self.busy.values()):
                self.chain[rw["id"]] = self.chain.get(o["id"], o["id"])
                self._dispatch(seat, rw["id"])

    async def _report(self) -> tuple[str, bool]:
        facts = self.r.report(self.inv)["markdown"]
        if not self.lead:
            return facts, False
        box: dict[str, Any] = {}
        tools = lead_tools(self.r, self.lead, self.inv, self.meter, report_box=box, roster=self.roster,
                           order_author=HARNESS)
        user = ("Write the final report. Call report_facts and start from it; write your interpretation under the "
                "facts; end with the answers in the format the task asks for; submit_report. If it is refused, fix "
                "exactly what it names and submit again.")
        try:
            await self._lead_turns(user, tools, "report", self.lead_turns)
        except Exception as e:  # noqa: BLE001
            self._ev("report_error", why=str(e)[:200])
        if box.get("text"):
            return str(box["text"]), True
        return facts + "\n\n*(The lead did not submit an interpretation that passed the record's check.)*", False
