"""
The scheduler makes no model calls. It issues orders from the question board, settles the ones whose predicates
are met, reworks the rest (twice), cancels what became moot, and brings in the lead seat only at exceptions and
for the report. Workers run in parallel as asyncio tasks; the record's leases keep them off each other's work.
Every scheduler action is already an event in the record (orders are task nodes, acceptance a decision), so the
run's audit trail is the record itself.

Under a profile with a workflow (hypgraph's ``@2`` profiles) the scheduler asks the record which **stage** each
question is in and issues that stage's order: the gates from the current stage up to the next review, as the
order's done-when, to the seat the stage names; a review stage goes to a reviewer, on the node the previous gate
produced. The question is complete when the record says so (``stages``), never when a seat says so.

With a ``World`` (``run(..., watch=True)``) each round also starts by syncing the record with the world: a file whose
bytes changed, a new head of the working tree, a page that no longer says what a source quotes (world.py). Results
that went stale are re-run by the instrument on the current files (``reproduce_result(support_claims=True)``): when
every value reproduces, the claims on them are fresh again with no model call; when a value moved, the answer's
review stage becomes a *refresh* order to a worker — recompute from the current files, write the claim again.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from hypgraph import GraphError

from .assemble import assembled_report
from .budget import BudgetExhausted, Meter
from .messages import Message, Tool
from .providers.base import ChatModel
from .record import HARNESS, INSTRUMENT, LocalRecord
from .reproduce import Reproducer, reproduce_result
from .seats import Seat, fit
from .telemetry import NULL, Telemetry, trace_tools
from .tools import OnWrite, lead_tools
from .worker import WorkerResult, await_external, run_agent_order, run_order
from .world import World

log = logging.getLogger("hypswarm.scheduler")

_REVIEW_GATES = {"reviewed": "CL", "result_reviewed": "RS"}    # a review gate → the code prefix of what it reviews
# gates that produce a result, and so can be satisfied again by recomputing: a refresh order asks for a new result
# and a new claim — whether the new result passes is the stage machinery's call (a failing suite is an answer too)
_RESULT_GATES = {"result_exists", "tests_pass_current", "tests_pass", "backtested", "backtested_oos", "solved",
                 "feasible_bounded", "run_registered"}


def _to_review(row: dict[str, Any]) -> str:
    """The answer a review should go to: the newest the record lists as unchecked (a checked answer beside it doesn't
    settle the question), else the newest answer (records before the ``unchecked`` field)."""
    pending = row.get("unchecked") or []
    return str(pending[-1] if pending else row["answers"][-1])


MAX_CRASHES = 3      # a seat whose orders end in an error this many times in a row is benched for the run
_DECIDE = ("rework", "cancel_work", "add")
LEAD_DECIDES = ("This is your last turn on this exception: decide now. rework the order with what is missing and, if a "
                "predicate can't be met as asked, a changed done_when; or cancel_work with the reason. Reading is no "
                "longer available.")


@dataclass
class SchedulerResult:
    stopped: str = ""                       # settled | budget | stuck | cancelled
    rounds: int = 0
    orders_issued: int = 0
    reworks: int = 0
    escalations: int = 0                    # orders the lead had to judge
    model_escalations: int = 0              # dispatches on a seat's deeper model (after a NOT MET)
    adopted: int = 0                        # orders taken over from a previous run (resume)
    reproductions: int = 0                  # results the instrument re-executed (no model calls)
    world_changes: int = 0                  # changes the world watcher found (files, heads, pages)
    reverifications: int = 0                # stale results the instrument re-ran on the current files
    refreshes: int = 0                      # orders to recompute an answer whose evidence moved
    lead_calls: int = 0
    report: str = ""
    report_accepted: bool = False           # the lead's report passed the record's check
    report_source: str = ""                 # "lead" | "assembled" (the harness, from the current claims) | ""
    workers: list[WorkerResult] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    lead_log: list[dict[str, Any]] = field(default_factory=list)   # one row per lead model call
    notices: list[dict[str, Any]] = field(default_factory=list)
    benched: list[str] = field(default_factory=list)  # seats taken out after MAX_CRASHES failures in a row


class Scheduler:
    def __init__(self, record: LocalRecord, inv: str, seats: Sequence[Seat], model_for: Callable[[Seat], ChatModel],
                 meter: Meter, *, data_tools: Sequence[Tool] = (), preamble: str = "", max_reworks: int = 2,
                 lease_minutes: int = 240, lead_turns: int = 6,
                 on_return: Callable[[Scheduler, int], None] | None = None, external_poll_s: float = 1.0,
                 external_timeout_s: float | None = None, header: str = "", reproducer: Reproducer | None = None,
                 world: World | None = None, on_write: OnWrite | None = None, assemble_report: bool = True,
                 tel: Telemetry | None = None, tel_parent: str = ""):
        self.r, self.inv, self.seats = record, inv, list(seats)
        self.model_for, self.meter = model_for, meter
        self.data_tools, self.preamble, self.header = list(data_tools), preamble, header
        self.reproducer = reproducer                        # host-supplied: re-executes registered code (no model)
        self._reproduced: set[str] = set()
        self.world = world                                  # host-supplied: keeps the record in step with the files
        self.on_write = on_write                            # host hook on every accepted write by a seat
        self.assemble_report = assemble_report              # no passing report from the lead: write it from the record
        self.tel, self.tel_parent = tel or NULL, tel_parent  # telemetry: spans for orders, model and tool calls
        self._order_spans: dict[asyncio.Task[WorkerResult], str] = {}
        self._reverified: set[tuple[str, str]] = set()      # (result, why it was stale) already re-run
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
        self.crashes: dict[str, int] = {}                   # seat → orders ended in an error, in a row
        self.notices: list[str] = []
        self._reissued: set[str] = set()                    # unreviewable claims already re-issued to a worker

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
        if self.tel.on:                                     # every scheduler decision, as telemetry too
            said: dict[str, Any] = {k: v if isinstance(v, (int, float, bool)) or v is None else str(v)[:300]
                                    for k, v in kw.items() if k not in ("span", "parent", "kind")}
            self.tel.emit("decision", parent=self.tel_parent, event=kind, **said)

    def stop(self) -> None:
        self._stop = True

    # ── dispatch ─────────────────────────────────────────────
    def _idle(self, pool: Sequence[Seat]) -> list[Seat]:
        return [s for s in pool if s.name not in self.busy]

    def _pick(self, pool: Sequence[Seat], text: str, ttype: str) -> Seat | None:
        idle = self._idle(pool)
        return max(idle, key=lambda s: (fit(s, text, ttype), -self.seats.index(s))) if idle else None

    def _model(self, seat: Seat, escalate: bool) -> ChatModel:
        """The seat's model — or, when the record has sent its work back once already and the seat names a deeper
        model, that one. Escalation is decided by the record's NOT MET, never by the model's own say-so."""
        if escalate and seat.escalate_to and seat.escalate_to != seat.model:
            return self.model_for(replace(seat, model=seat.escalate_to))
        return self.model_for(seat)

    def _dispatch(self, seat: Seat, order: str, escalate: bool = False) -> None:
        # A seat that returns at once at no cost — an agent that crashes (its reservation is released), or any seat
        # once only the report's calls are left — kept a task in flight every round, so the run never reached its
        # stop: each return was reworked or cancelled for free and, once the clock moved, a fresh order was issued
        # ("no live claim since the order was issued") and dispatched again. Hung CI on a slower runner.
        if seat.name in self.res.benched or (not seat.external and self.meter.orders_spent()):
            self._ev("not_dispatched", seat=seat.name, order=self.r.get(order)["code"],
                     why="benched" if seat.name in self.res.benched else "only the report's calls are left")
            return
        self.busy[seat.name] = order
        code = self.r.get(order)["code"]
        model: ChatModel | None = None
        if seat.external:
            model_name = "external"
        elif seat.agent is not None:
            model_name = "agent:" + str(getattr(seat.agent, "__name__", type(seat.agent).__name__))
        else:
            model = self._model(seat, escalate)
            model_name = getattr(model, "name", "?")
        sp = self.tel.start("order", parent=self.tel_parent, seat=seat.name, order=code, role=seat.role, model=model_name,
                            escalated=bool(escalate) or None)
        task: asyncio.Task[WorkerResult]
        if seat.external:
            task = asyncio.create_task(await_external(seat, self.r, self.inv, order, timeout_s=self.external_timeout_s,
                                                      poll_s=self.external_poll_s))
        elif seat.agent is not None:
            task = asyncio.create_task(run_agent_order(seat, self.r, self.inv, order, meter=self.meter,
                                                       data_tools=self.data_tools, preamble=self._preamble(),
                                                       header=self.header, on_write=self.on_write, tel=self.tel,
                                                       tel_parent=sp))
        else:
            assert model is not None
            task = asyncio.create_task(run_order(seat, model, self.r, self.inv, order, meter=self.meter,
                                                 data_tools=self.data_tools, preamble=self._preamble(),
                                                 header=self.header, on_write=self.on_write, tel=self.tel,
                                                 tel_parent=sp))
        self._order_spans[task] = sp
        self.inflight[task] = (seat, order)
        escalated = bool(escalate and seat.escalate_to and seat.escalate_to != seat.model and not seat.external)
        if escalated:
            self.res.model_escalations += 1
        self._ev("dispatch", seat=seat.name, order=self.r.get(order)["code"], external=seat.external,
                 model=model_name, escalated=escalated)

    def _adopt(self) -> None:
        """Resume: take over the orders a previous run of this investigation left open. An open or overdue order
        assigned to one of our seats is dispatched again (its earlier writes are in the record and still count);
        one assigned to nobody here is cancelled with the reason. Rework chains are read back from the record's
        ``supersedes`` links, so the rework cap and escalation carry over."""
        for o in self.r.orders(self.inv):
            if o["status"] not in ("open", "overdue"):
                continue
            root, depth = o["id"], 0
            while True:                                 # follow supersedes to the first order of the chain
                older = [e["dst"] for e in self.r.get(root).get("out", []) if e["rel"] == "supersedes"]
                if not older:
                    break
                root, depth = older[0], depth + 1
            self.chain[o["id"]] = root
            self.reworked[root] = max(self.reworked.get(root, 0), depth)
            seat = next((s for s in self.seats if s.name == o["assignee"]), None)
            if seat is None:
                self.r.cancel_work(author=HARNESS, order=o["id"], why=f"resumed without a seat named {o['assignee']!r}")
                self._ev("cancelled", order=o["code"], why="no such seat on resume")
                continue
            if seat.name in self.busy:
                continue                                # one order per seat; the other stays open for a later round
            self.res.adopted += 1
            self._ev("adopt", seat=seat.name, order=o["code"], reworks=depth)
            self._dispatch(seat, o["id"], escalate=depth > 0)

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
    async def _reproduce_new(self) -> None:
        """Every result an author registered with its code is re-executed once by the instrument, before any
        reviewer sees it. Mechanical verification costs no model call; the reviewer's calls go to judgement."""
        if not self.reproducer:
            return
        for r in self.r.search("", "result", self.inv, 500):
            if r["id"] in self._reproduced or r.get("by") == INSTRUMENT:
                continue
            self._reproduced.add(r["id"])
            try:
                out = await reproduce_result(self.r, self.inv, r["id"], self.reproducer)
            except GraphError as e:
                self._ev("reproduce_failed", result=r.get("code"), why=str(e)[:200])
                continue
            if out:
                self.res.reproductions += 1
                self._ev("reproduced", result=r.get("code"), ok=out["ok"], run=out["run"], confirmed=out["confirmed"],
                         unprinted=out["unprinted"], contradicted=out["contradicted"], missing=out["missing"])

    def _sync_world(self) -> None:
        """The record catches up with the world: changed files, a new head, a page that moved (world.py)."""
        if not self.world:
            return
        try:
            notes = self.world.sync()
        except GraphError as e:
            self._ev("world_sync_failed", why=str(e)[:200])
            return
        for n in notes:
            if n not in self.notices:
                self.notices.append(n)
            self.res.notices.append({"t": round(time.time(), 3), "text": n, "stale": [], "added": [],
                                     "after_calls": self.meter.total.calls, "by": "world"})
        if notes:
            self.res.world_changes += len(notes)
            self._ev("world_changed", notes=[n[:160] for n in notes])

    async def _reverify(self) -> None:
        """Every result that went stale is re-run once per reason on the current files. Unchanged values bring its
        claims back (the lab result supports them); a moved value leaves them stale for a refresh order."""
        if not self.reproducer:
            return
        for r in self.r.search("", "result", self.inv, 500):
            if r.get("by") == INSTRUMENT:
                continue
            why = "; ".join((r.get("state") or {}).get("stale") or [])
            if not why or (r["id"], why) in self._reverified:
                continue
            self._reverified.add((r["id"], why))
            try:
                out = await reproduce_result(self.r, self.inv, r["id"], self.reproducer, support_claims=True)
            except GraphError as e:
                self._ev("reverify_failed", result=r.get("code"), why=str(e)[:200])
                continue
            if out:
                self.res.reverifications += 1
                self._ev("reverified", result=r.get("code"), run=out["run"], confirmed=out["confirmed"],
                         contradicted=out["contradicted"], unprinted=out["unprinted"], supported=out["supported"],
                         because=why[:160])

    def _settle_and_rework(self) -> None:
        moot = self.r.cancel_moot(author=HARNESS, inv=self.inv)
        for m in moot:
            self._ev("cancel_moot", order=m["order"], because=m["because"])
        for d in self.r.settle(author=HARNESS, inv=self.inv):
            self._ev("settled", order=d["order"], decision=d["decision"])
        rows = self._stage_rows()
        complete_qs = {q["question"] for q in rows if q["complete"]} if rows else set()
        for o in self.r.orders(self.inv, status="returned"):
            chk = self.r.check_work(o["id"])
            if chk["all_met"]:
                continue
            if o["target_id"] in complete_qs:
                # the record settled the question another way (a checked inconclusive answer): the order's gates no
                # longer matter, and a rework would ask for work the record no longer needs
                self.r.cancel_work(author=HARNESS, order=o["id"], why="the question is complete in the record; the "
                                   "order's remaining gates are moot")
                self._ev("cancelled", order=o["code"], why="question complete")
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
                self._dispatch(seat, rw["order"], escalate=True)
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

    # ── stages: the workflow's orders ────────────────────────
    def _stage_rows(self) -> list[dict[str, Any]] | None:
        """Each question's derived stage from the record, or None when the profile has no workflow (frozen @1, no
        profile) or the record can't say (an older hypgraph / server)."""
        try:
            rows = list(self.r.stages(self.inv) or [])
        except (AttributeError, GraphError, KeyError, NotImplementedError, TypeError):
            return None
        if not rows or not all(r.get("workflow") for r in rows):
            return None
        return rows

    def _pick_for_stage(self, pool: Sequence[Seat], who: str, text: str) -> Seat | None:
        """The seat a stage names (`quant`, `fact_checker`), when it is idle; else the best fit for the question."""
        idle = self._idle(pool)
        if not idle:
            return None
        tokens = set(re.findall(r"[a-z_]+", (who or "").lower()))
        named = [s for s in idle if s.name in tokens]
        if named:
            return named[0]
        return max(idle, key=lambda s: (fit(s, f"{who} {text}", "question"), -self.seats.index(s)))

    def _assign_from_stages(self, rows: list[dict[str, Any]]) -> None:
        busy_targets = {o["target_id"] for o in self.r.orders(self.inv) if o["status"] in ("open", "overdue", "returned")}
        answered = {b["id"]: b for b in self.r.question_board(self.inv) if b["status"] == "answered"}
        for q in rows:
            if q["complete"]:
                continue
            gates = q["gates"]
            i = next((k for k, gt in enumerate(gates) if not gt["met"] and not gt["optional"]), None)
            if i is None:
                continue
            first = gates[i]
            text = str((self.r.get(q["question"]).get("body") or {}).get("text") or "")
            # an unchecked claim already answers the question while an earlier gate is still open (an honest
            # "it can't be answered", or an answer written ahead of its hypothesis): the review comes first — a
            # checked inconclusive answer settles the question, and a checked finding tells the worker what stands
            rev = next((k for k, gt in enumerate(gates) if gt["gate"] == "reviewed"), None)
            if q["question"] in answered and rev is not None and not gates[rev]["met"] and i < rev:
                b = answered[q["question"]]
                code = _to_review(b)
                try:
                    claim = self.r.resolve(code, self.inv)
                except (GraphError, KeyError, IndexError):
                    claim = ""
                if claim and claim not in busy_targets and not self._stale(claim):
                    self._issue_review_on(q, gates[rev], claim, code, text, busy_targets)
            if q["question"] in busy_targets:
                continue
            if first["gate"] in _REVIEW_GATES:
                self._issue_review_stage(q, gates, i, text, busy_targets)
                continue
            run = []
            for gt in gates[i:]:
                if gt["optional"]:
                    continue
                if gt["gate"] in _REVIEW_GATES:
                    break
                run.append(gt)
            seat = self._pick_for_stage(self.workers, first["who"], text)
            objective = (f"{q['code']} is at stage '{first['stage']}' ({q['index']}/{q['of']}) of the {q['profile']} "
                         f"workflow — {first['why']}. Move it through {', '.join(gt['stage'] for gt in run)}: "
                         f"{text}")
            if seat and self._issue(seat, q["question"], objective, [{"p": gt["gate"]} for gt in run]):
                self._ev("stage_order", question=q["code"], stage=first["stage"], gates=[gt["gate"] for gt in run],
                         seat=seat.name)
                busy_targets.add(q["question"])

    def _issue_review_stage(self, q: dict[str, Any], gates: list[dict[str, Any]], i: int, text: str,
                            busy_targets: set[str]) -> None:
        """A review stage: the order goes to a reviewer who didn't write the node, on the node the reviewed gate
        produced (the newest claim for `reviewed`, the solve result for `result_reviewed`)."""
        first = gates[i]
        prefix = _REVIEW_GATES[first["gate"]]
        # the newest node of the reviewed kind that an earlier, met gate produced (a claim for `reviewed`, whatever
        # the profile calls that gate — claim_made, sourced; a result for `result_reviewed`)
        codes = [c for gt in gates[:i] if gt["met"] for c in gt.get("evidence") or []
                 if re.fullmatch(prefix + r"\d+", str(c))]
        if not codes:
            return
        ids: list[tuple[str, str]] = []
        for c in dict.fromkeys(codes):
            try:
                ids.append((c, self.r.resolve(c, self.inv)))
            except (GraphError, KeyError):
                continue
        fresh = [(c, x) for c, x in ids if not self._stale(x)]
        # a checked answer beside an unchecked one: the unchecked one is what keeps the question open (the record
        # settles a question once every live answer is checked; studies T1, opposed answers)
        unchecked = [(c, x) for c, x in fresh if self._review_state(x) != "checked"]
        if unchecked:
            fresh = unchecked
        if fresh:
            self._issue_review_on(q, first, fresh[-1][1], fresh[-1][0], text, busy_targets)
        elif ids:
            self._issue_refresh(q, gates, i, text, ids[-1][0], ids[-1][1], busy_targets)

    def _beside(self, question: str, code: str) -> str:
        """For a review of a second answer: the checked answers it sits beside, and what the reviewer is to judge."""
        row = next((b for b in self.r.question_board(self.inv) if b["id"] == question), None)
        if not row or code not in (row.get("unchecked") or []):
            return ""
        checked = [a for a in row["answers"] if a not in row["unchecked"]]
        if not checked:
            return ""
        return (f" {code} sits beside {', '.join(checked)}, already checked, on the same question. Read them side by "
                "side: if they disagree, the files decide which is right — object to the wrong one, even if its numbers "
                "reproduce (a re-run confirms the numbers, not what they mean). The question settles only when every "
                "live answer to it is checked.")

    def _review_state(self, nid: str) -> str:
        try:
            return str(((self.r.get(nid).get("state") or {}).get("review") or {}).get("state") or "unchecked")
        except (GraphError, KeyError):
            return ""

    def _stale(self, nid: str) -> list[str]:
        try:
            return list((self.r.get(nid).get("state") or {}).get("stale") or [])
        except (GraphError, KeyError):
            return []

    def _issue_refresh(self, q: dict[str, Any], gates: list[dict[str, Any]], i: int, text: str, code: str, nid: str,
                       busy_targets: set[str]) -> None:
        """The answer's evidence moved (the instrument's re-run on the current files didn't reproduce it): a worker
        recomputes and writes the claim again. A review of the stale claim would be wasted — it can't count."""
        if q["question"] in busy_targets:
            return
        why = "; ".join(self._stale(nid)[:2]) or "what it rests on has changed"
        who = next((gt["who"] for gt in gates[:i] if gt["gate"] in _RESULT_GATES), gates[i]["who"])
        seat = self._pick_for_stage(self.workers, who, text)
        objective = (f"{q['code']}'s answer {code} rests on evidence that is now stale — {why}. The instrument re-ran it on "
                     "the current files and it did not reproduce. Recompute from the files as they are now (the notices "
                     f"say what changed), register the run, and write the claim again; link the new claim supersedes "
                     f"{code}. The question: {text}")
        if seat and self._issue(seat, q["question"], objective, [{"p": "result_exists"}, {"p": "claim_made"}]):
            self.res.refreshes += 1
            self._ev("refresh_order", question=q["code"], stale=code, why=why[:160], seat=seat.name)
            busy_targets.add(q["question"])

    def _issue_review_on(self, q: dict[str, Any], first: dict[str, Any], target: str, code: str, text: str,
                         busy_targets: set[str]) -> None:
        if target in busy_targets:
            return
        author = self.r.get(target)["by"]
        pool = [s for s in self.reviewers if s.name != author]
        if not pool:
            if target in self._reissued or q["question"] in busy_targets:
                return
            self._reissued.add(target)
            worker = self._pick(self.workers, text, "question")
            if worker and self._issue(worker, q["question"], f"Answer {q['code']}: {text} — {code} by {author} "
                                      "can't be reviewed (its author is the reviewer); write the answer as your own "
                                      "claim, from the files.", [{"p": "claim_made"}]):
                self._ev("unreviewable", claim=code, by=author, reissued_to=worker.name)
                busy_targets.add(q["question"])
            return
        seat = self._pick_for_stage(pool, first["who"], text)
        what = "claim" if first["gate"] == "reviewed" else "result"
        objective = (f"{q['code']} is at stage '{first['stage']}' ({q['index']}/{q['of']}) of the {q['profile']} "
                     f"workflow. Review {code}, the {what} that answers it: the order lists it, its values and "
                     "what it rests on" + (", and what the instrument's re-run confirmed — recompute only a value it "
                     "CONTRADICTED; a value merely not printed is not evidence against" if self.reproducer else "")
                     + ". Judge the method and the wording against the question; record a verdict."
                     + self._beside(q["question"], code))
        if seat and self._issue(seat, target, objective, [{"p": first["gate"]}]):
            self._ev("stage_order", question=q["code"], stage=first["stage"], gates=[first["gate"]], seat=seat.name)
            busy_targets.add(target)

    def _assign(self) -> None:
        if self.meter.warn():
            return                                          # drain; the report is next
        rows = self._stage_rows()
        if rows is not None:
            self._assign_from_stages(rows)
            return
        board = self.r.question_board(self.inv)
        busy_targets = {o["target_id"] for o in self.r.orders(self.inv) if o["status"] in ("open", "overdue", "returned")}
        for q in board:
            if q["status"] == "open" and q["id"] not in busy_targets:
                seat = self._pick(self.workers, q["text"], "question")
                if seat and self._issue(seat, q["id"], f"Answer {q['code']}: {q['text']}"):
                    busy_targets.add(q["id"])
            elif q["status"] == "answered" and self.reviewers:
                code = _to_review(q)
                claim = self.r.resolve(code, self.inv)
                if claim in busy_targets:
                    continue
                author = self.r.get(claim)["by"]
                pool = [s for s in self.reviewers if s.name != author]
                if not pool:
                    # The only reviewer wrote the answer (a reviewer seat on a served record, an outside seat): nobody
                    # here may review it, so the question would never settle. Ask a worker for the answer instead —
                    # once per such claim; if the worker's answer doesn't displace it, the lead sees it in the report.
                    if q["id"] in busy_targets or claim in self._reissued:
                        continue
                    self._reissued.add(claim)
                    worker = self._pick(self.workers, q["text"], "question")
                    if worker and self._issue(worker, q["id"], f"Answer {q['code']}: {q['text']} — {code} "
                                              f"by {author} can't be reviewed (its author is the reviewer); write the "
                                              "answer as your own claim, from the files."):
                        self._ev("unreviewable", claim=code, by=author, reissued_to=worker.name)
                        busy_targets.add(q["id"])
                    continue
                seat = self._pick(pool, q["text"], "claim")
                objective = (f"Review {code}, which answers {q['code']}. The order lists the claim, its "
                             "measurements and the results it rests on" + (", and what the instrument's re-run of the "
                             "author's code confirmed — recompute only a value it CONTRADICTED; a value merely not "
                             "printed is not evidence against" if self.reproducer else "") +
                             ". Judge the method and the wording against the question; record a verdict."
                             + self._beside(q["id"], code))
                if seat and self._issue(seat, claim, objective, [{"p": "reviewed"}]):
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

    def _record_complete(self) -> bool:
        try:
            c = self.r.completion(self.inv)
        except (GraphError, KeyError, AttributeError):
            return False
        return bool(c.get("complete")) and bool(c.get("pinned", True))

    def _done(self) -> str:
        rows = self._stage_rows()
        if rows is not None:                                # the workflow's word on done, question by question
            if all(q["complete"] for q in rows) and not self.inflight:
                return "settled"
            if not self.inflight and self._record_complete():
                # The profile's completion criteria are its definition of done: a trading desk that declined once
                # is done, even if one question's own `positioned` gate wants a decision based on its claim
                # (studies T2: complete at the record, then three reworks and the rest of the budget on Q3)
                return "settled"
            if not self.inflight and not self._pending_lead:
                open_orders = [o for o in self.r.orders(self.inv) if o["status"] in ("open", "overdue", "returned")]
                if not open_orders:
                    return "stuck" if any(not q["complete"] for q in rows) else "settled"
            return ""
        board = self.r.question_board(self.inv)
        if board and all(q["status"] in ("settled", "contested") for q in board) and not self.inflight:
            return "settled"
        if not self.inflight and not self._pending_lead:
            open_orders = [o for o in self.r.orders(self.inv) if o["status"] in ("open", "overdue", "returned")]
            if not open_orders:
                return "stuck" if any(q["status"] in ("open", "answered", "in progress") for q in board) else "settled"
        return ""

    # ── the loop ─────────────────────────────────────────────
    async def run(self, *, adopt: bool = False) -> SchedulerResult:
        if adopt:
            self._adopt()
        while not self._stop:
            self.res.rounds += 1
            try:
                self._sync_world()
                await self._reproduce_new()
                await self._reverify()
                self._settle_and_rework()
                while self._pending_lead:
                    o, missing = self._pending_lead.pop(0)
                    await self._lead_judges(o, missing)
                self._assign()
            except BudgetExhausted as e:
                self.res.stopped = f"budget: {e}"
                break
            why = self._done()
            if (why == "stuck" or (not why and not self.inflight)) and self.meter.orders_spent():
                why = "budget: only the report's calls are left"
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
                if str(wr.stopped).startswith("error"):
                    self.crashes[seat.name] = self.crashes.get(seat.name, 0) + 1
                    if self.crashes[seat.name] >= MAX_CRASHES and seat.name not in self.res.benched:
                        self.res.benched.append(seat.name)
                        self._ev("benched", seat=seat.name, why=f"{MAX_CRASHES} orders in a row ended in an error; "
                                 f"last: {str(wr.stopped)[:160]}")
                else:
                    self.crashes[seat.name] = 0
                self.tel.end(self._order_spans.pop(t, ""), ok=not str(wr.stopped).startswith("error"),
                             error=wr.stopped if str(wr.stopped).startswith("error") else "", calls=wr.calls,
                             returned=wr.returned, by_record=wr.returned_by_record or None, stopped=wr.stopped or None)
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
            self.tel.end(self._order_spans.pop(t, ""), ok=False, error="cancelled: the run stopped")
        if self._stop and not self.res.stopped:
            self.res.stopped = "stopped"                    # the host called stop(); the record keeps the open orders
        self.res.report, self.res.report_accepted = await self._report()
        return self.res

    # ── the lead ─────────────────────────────────────────────
    async def _lead_turns(self, user: str, tools: list[Tool], unit: str, turns: int) -> None:
        assert self.lead
        model = self.model_for(self.lead)
        tools = trace_tools(tools, self.tel, parent=self.tel_parent, seat=self.lead.name, order=unit)
        messages = [Message("system", (self.header + "\n" if self.header else "") + self.lead.prompt() + "\n\n"
                            + self._preamble()), Message("user", user)]
        by = {t.name: t for t in tools}
        last, retried, turn = turns - 1, False, -1
        while turn < last:
            turn += 1
            offered = tools
            if turn >= turns - 1 and "submit_report" in by and len(by) > 1:
                # the last turn of the report phase submits: a careful lead otherwise reads (show, briefing) until
                # its turns run out and leaves the run without a report (studies/challenges E1)
                offered = [by["submit_report"]]
                messages.append(Message("user", "This is your last turn. Submit the report now with submit_report: "
                                                "the facts you have, your interpretation under them, and the answers. "
                                                + ("Your last submit was refused: fix exactly what it named. "
                                                   if retried else "") + "Nothing else is available."))
            elif turn >= turns - 1 and "submit_report" not in by and any(n in by for n in _DECIDE):
                # an exception ends on a decision: leads read the record (show, two to five a turn) until their turns
                # ran out, and the order was cancelled as undecided (studies S2, day 2: three of four escalations)
                offered = [by[n] for n in _DECIDE if n in by]
                messages.append(Message("user", LEAD_DECIDES + (" Your last decision was refused: fix exactly what it "
                                                                "named." if retried else "")))
            try:
                self.meter.reserve(unit)
            except BudgetExhausted:
                return
            t0 = time.time()
            mid = self.tel.start("model", parent=self.tel_parent, seat=self.lead.name, order=unit,
                                 model=getattr(model, "name", ""))
            try:
                reply = await model.complete(messages, offered, temperature=self.lead.temperature, unit=unit)
            except Exception as e:
                self.tel.end(mid, ok=False, error=f"{type(e).__name__}: {e}")
                self.meter.release(unit)
                raise
            self.meter.add(unit, reply.input_tokens, reply.cached_tokens, reply.output_tokens)
            used: dict[str, Any] = {"in": reply.input_tokens, "cached": reply.cached_tokens,
                                    "out": reply.output_tokens,
                                    "usd": self.tel.usd(reply.input_tokens, reply.cached_tokens, reply.output_tokens),
                                    "tool_calls": [tc.name for tc in reply.tool_calls], "text": self.tel.text(reply.content)}
            self.tel.end(mid, **used)
            self.res.lead_calls += 1
            self.res.lead_log.append({"t": round(t0, 3), "s": round(time.time() - t0, 3), "unit": unit,
                                      "agent": self.lead.name, "in": reply.input_tokens,
                                      "cached": reply.cached_tokens, "out": reply.output_tokens,
                                      "tools": [tc.name for tc in reply.tool_calls],      # a lost report shows why
                                      "said": (reply.content or "")[:300]})
            messages.append(reply.as_message())
            if not reply.tool_calls:
                if "submit_report" in by and len(by) > 1 and turn < last:
                    # a reply with no call doesn't end the report phase: the next turn is the submit-only one
                    # (studies/challenges S1: an empty fifth turn left the run without a report)
                    turn = last - 1
                    continue
                return
            avail = {t.name for t in offered}
            for tc in reply.tool_calls:
                tool = by.get(tc.name) if tc.name in avail else None
                out = (await tool.call(tc.args) if tool else
                       f"error: only {', '.join(sorted(avail))} is available now" if tc.name in by else
                       f"error: no tool {tc.name!r}")
                messages.append(Message("tool", out[:12000], tool_call_id=tc.id))
                if tc.name == "submit_report" and out == "report accepted":
                    return
                if tc.name == "submit_report" and turn == last and not retried:
                    # refused on the last turn: one more submit-only turn, with the refusal in hand, before the
                    # harness assembles (studies/challenges E2: refused on turns 5 and 6 of 6, both rightly)
                    last, retried = last + 1, True
                if tc.name in _DECIDE and turn == last and not retried and out.startswith("refused"):
                    # the same for an exception's last decision: a refused rework left the order undecided and the
                    # harness cancelled it (studies S2, day 2)
                    last, retried = last + 1, True

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

    def _report_kind(self) -> str:
        """The profile's name for its report ('Change report', 'Desk note'), when the profile has a workflow."""
        try:
            from hypgraph import profiles as _gp
            pid = str((self.r.get(self.inv).get("body") or {}).get("profile") or "")
            w = getattr(_gp.get(pid), "workflow", None) if pid else None
            return str(w.report) if w else ""
        except Exception:  # noqa: BLE001 — a missing profile never costs the report
            return ""

    async def _report(self) -> tuple[str, bool]:
        facts = self.r.report(self.inv)["markdown"]
        if not self.lead:
            return facts, False
        box: dict[str, Any] = {}
        # The run is ending: the report phase gets reading and submitting only. Planning tools (add, rework,
        # cancel) belong to exceptions — a lead that spent its report turns adding questions nobody will work left
        # the run without a report (F7-907, pilot 4).
        tools = [t for t in lead_tools(self.r, self.lead, self.inv, self.meter, report_box=box, roster=self.roster,
                                       order_author=HARNESS) if t.name in ("briefing", "report_facts", "submit_report",
                                                                             "show")]
        kind = self._report_kind()
        user = (f"Write the final report{' — the ' + kind if kind else ''}. Call report_facts and start from it; "
                "write your interpretation under the facts; end with the answers in the format the task asks for. "
                "Every number in an answer must be one a claim already binds: copy it from report_facts, don't "
                "recompute or average it. submit_report. If it is refused, fix exactly what it names and submit "
                "again. Nothing else can be "
                "done now: the run is ending.")
        try:
            await self._lead_turns(user, tools, "report", self.lead_turns)
        except Exception as e:  # noqa: BLE001
            self._ev("report_error", why=str(e)[:200])
        if box.get("text"):
            self.res.report_source = "lead"
            return str(box["text"]), True
        self._ev("report_missing", refusals=box.get("refusals", 0), refused=(box.get("refused") or [])[-3:])
        if self.assemble_report:
            try:
                text = assembled_report(self.r, self.inv)
            except Exception as e:  # noqa: BLE001 — a failed assembly leaves the facts, as before
                self._ev("report_assembly_error", why=str(e)[:200])
                text = ""
            if text:
                self.res.report_source = "assembled"
                self._ev("report_assembled")
                return text, False
        return facts + "\n\n*(The lead did not submit an interpretation that passed the record's check.)*", False
