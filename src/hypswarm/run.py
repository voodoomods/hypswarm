"""The public API: run a task with seats on a record, under a budget."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .budget import Budget, Meter, Pricing
from .messages import Tool
from .providers.base import ChatModel
from .record import LocalRecord
from .scheduler import Scheduler, SchedulerResult
from .seats import Seat

log = logging.getLogger("hypswarm")

ANSWER_FORMAT = ("End the report with a fenced block that starts with ```answers and holds one JSON object: each "
                 "question code → the answer (null if unanswered).")


@dataclass(frozen=True)
class Task:
    title: str
    mission: str
    questions: Sequence[tuple[str, str]]          # (code, text): ("Q1", "What is …?")
    files: Mapping[str, bytes] = field(default_factory=dict)
    success: str = ""
    answer_format: str = ANSWER_FORMAT
    notes: str = ""                               # anything every seat should know (tools, conventions)
    header: str = ""                              # the first line of every seat's system prompt (e.g. a run id, so no
                                                  # two runs share a prompt prefix with a provider's cache — pilot 4)
    profile: str = ""                             # governance profile: scientific | software | trading | knowledge |
                                                  # optimization (or a pinned id such as software@1); see profiles.py

    def preamble(self) -> str:
        qs = "\n".join(f"- {c}: {t}" for c, t in self.questions)
        files = ", ".join(sorted(self.files)) or "none"
        notes = self.notes
        if self.profile:
            from .profiles import get as _profile
            sp = _profile(self.profile)
            notes = (f"PROFILE {sp.id} — {sp.about}\n{sp.notes}" + (f"\n{self.notes}" if self.notes else ""))
        return (f"MISSION\n{self.mission}\n\nQUESTIONS\n{qs}\n\nFILES: {files}\n\nFINAL ANSWER FORMAT\n"
                f"{self.answer_format}" + (f"\n\nNOTES\n{notes}" if notes else ""))


@dataclass
class RunResult:
    inv: str
    record_path: str
    stopped: str
    report: str
    report_accepted: bool
    board: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    usage: dict[str, Any]
    scheduler: SchedulerResult
    seconds: float
    run_node: str

    def answers(self) -> dict[str, Any] | None:
        import re
        m = re.findall(r"```answers\s*(\{.*?\})\s*```", self.report, re.DOTALL)
        if not m:
            return None
        try:
            d = json.loads(m[-1])
        except json.JSONDecodeError:
            return None
        return d if isinstance(d, dict) else None


ModelSpec = ChatModel | Mapping[str, ChatModel] | Callable[[Seat], ChatModel]


def _model_for(models: ModelSpec, default: ChatModel | None) -> Callable[[Seat], ChatModel]:
    if hasattr(models, "complete"):
        fixed: ChatModel = models  # type: ignore[assignment]
        return lambda s: fixed
    if callable(models):
        return models
    table: Mapping[str, ChatModel] = models

    def pick(seat: Seat) -> ChatModel:
        m = table.get(seat.name) or table.get(seat.model) or table.get(seat.role) or default or table.get("*")
        if m is None:
            raise ValueError(f"no model for seat {seat.name!r}")
        return m
    return pick


async def run(task: Task, seats: Sequence[Seat] | None, models: ModelSpec, *, record: str | Path | Any = None,
              budget: Budget | None = None, pricing: Pricing | None = None, data_tools: Sequence[Tool] = (),
              spend: Any = None, external_meter: Callable[[], float] | None = None,
              default_model: ChatModel | None = None,
              on_return: Callable[[Scheduler, int], None] | None = None, lease_minutes: int = 240,
              external_poll_s: float = 1.0, external_timeout_s: float | None = None,
              resume: str = "", reproducer: Any = None, folder: str | Path | None = None,
              toolkits: Sequence[str] | None = None, watch: bool = False, refetch: Any = None,
              on_write: Any = None) -> RunResult:
    """Run ``task`` with ``seats`` on a record at ``record`` — a path, in memory, or a record client such as
    ``HttpRecord`` for a record served by ``hypgraph serve --writable`` — under ``budget``.
    ``models``: one model for every seat, a mapping by seat name / role / model id, or a function of the seat.
    ``resume``: the investigation (id or code) a previous run of this task left in the record — the task is not
    seeded again, orders left open are taken over, and this run is filed as a new run node that resumes it.
    ``reproducer``: ``(source) -> stdout`` (sync or async) that re-executes a worker's registered code in the host's
    sandbox; every result with code is re-run once by the instrument before review (see reproduce.py).
    ``seats=None`` takes the task's profile roster; ``toolkits`` names registry bundles built for the run (the
    profile's by default) over ``folder``, added to ``data_tools``.
    ``watch``: keep the record in step with the world each round (world.py) — files in ``folder`` whose bytes
    changed, and under the software workflow the working tree as a head that a commit supersedes; ``refetch(url) ->
    text`` adds the sources' pages. Stale results are then re-run on the current files and only the answers whose
    evidence moved are redone. ``on_write(kind, payload)`` is told after every write a seat makes."""
    sp = None
    if task.profile:
        from .profiles import get as _profile
        sp = _profile(task.profile)
    if seats is None:
        if not sp:
            raise ValueError("seats=None needs a task profile to take the roster from")
        seats = list(sp.seats)
    if not seats:
        raise ValueError("at least one seat")
    t0 = time.time()
    meter = Meter(budget or Budget(), pricing, external_meter)
    rec: Any = record if hasattr(record, "briefing") else LocalRecord(record, seats, spend=spend)
    if resume:
        inv = str(rec.resolve(resume))
        if rec.get(inv)["type"] != "investigation":
            raise ValueError(f"resume: {resume!r} is not an investigation")
    else:
        inv = rec.start(task.title, task.mission, task.questions, success=task.success, files=task.files,
                        reviewers=[s.name for s in seats if s.role == "reviewer"], profile=sp.id if sp else "")
    kits = list(toolkits) if toolkits is not None else (list(sp.toolkits) if sp else [])
    if kits:
        from .toolkits import ToolContext, build
        data_tools = list(data_tools) + build(kits, ToolContext(rec, inv, Path(folder) if folder else None))
    model_for = _model_for(models, default_model)
    from . import __version__
    config = {"hypswarm": __version__,
              "seats": [{"name": s.name, "role": s.role, "model": "external (MCP)" if s.external else ("agent:" + str(getattr(s.agent, "__name__", type(s.agent).__name__)) if s.agent is not None else model_for(s).name),
                         **({"escalate_to": s.escalate_to} if s.escalate_to else {})} for s in seats],
              "budget": {"max_calls": meter.budget.max_calls, "max_usd": meter.budget.max_usd},
              "preamble_sha256": hashlib.sha256(task.preamble().encode()).hexdigest(),
              "data_tools": [t.name for t in data_tools], **({"resumes": inv} if resume else {})}
    rid = rec.file_run(inv, config)
    world = None
    if watch or refetch:
        from .world import World
        wf = getattr(sp.record_profile, "workflow", None) if sp else None
        world = World(rec, inv, folder if watch else None, refetch=refetch,
                      tree=bool(watch and folder and wf and "diff" in getattr(wf, "artifacts", {})))
    sched = Scheduler(rec, inv, seats, model_for, meter, data_tools=data_tools, preamble=task.preamble(),
                      on_return=on_return, lease_minutes=lease_minutes, external_poll_s=external_poll_s,
                      external_timeout_s=external_timeout_s, header=task.header, reproducer=reproducer,
                      world=world, on_write=on_write)
    for s in seats:
        if s.external:
            log.info("external seat %s: %s", s.name, s.mcp_hint(str(rec.path)))
    try:
        sr = await sched.run(adopt=bool(resume))
        rec.finish_run(rid, "succeeded" if sr.stopped == "settled" else "interrupted", sr.stopped)
    except Exception as e:
        rec.finish_run(rid, "failed", f"{type(e).__name__}: {e}")
        raise
    out = RunResult(inv=inv, record_path=str(rec.path), stopped=sr.stopped, report=sr.report,
                    report_accepted=sr.report_accepted, board=rec.question_board(inv), orders=rec.orders(inv),
                    usage=meter.summary(), scheduler=sr, seconds=round(time.time() - t0, 1), run_node=rid)
    log.info("run %s: %s in %d calls, $%.4f", inv, sr.stopped, meter.total.calls, meter.usd)
    return out
