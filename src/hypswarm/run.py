"""The public API: run a task with seats on a record, under a budget."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

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

    def preamble(self) -> str:
        qs = "\n".join(f"- {c}: {t}" for c, t in self.questions)
        files = ", ".join(sorted(self.files)) or "none"
        return (f"MISSION\n{self.mission}\n\nQUESTIONS\n{qs}\n\nFILES: {files}\n\nFINAL ANSWER FORMAT\n"
                f"{self.answer_format}" + (f"\n\nNOTES\n{self.notes}" if self.notes else ""))


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
        m = re.findall(r"```answers\s*(\{.*?\})\s*```", self.report, re.S)
        if not m:
            return None
        try:
            return json.loads(m[-1])
        except json.JSONDecodeError:
            return None


ModelSpec = ChatModel | Mapping[str, ChatModel] | Callable[[Seat], ChatModel]


def _model_for(models: ModelSpec, default: ChatModel | None) -> Callable[[Seat], ChatModel]:
    if callable(models) and not hasattr(models, "complete"):
        return models  # type: ignore[return-value]
    if hasattr(models, "complete"):
        return lambda s: models  # type: ignore[return-value]
    table: Mapping[str, ChatModel] = models  # type: ignore[assignment]

    def pick(seat: Seat) -> ChatModel:
        m = table.get(seat.name) or table.get(seat.model) or table.get(seat.role) or default or table.get("*")
        if m is None:
            raise ValueError(f"no model for seat {seat.name!r}")
        return m
    return pick


async def run(task: Task, seats: Sequence[Seat], models: ModelSpec, *, record: str | Path | None = None,
              budget: Budget | None = None, pricing: Pricing | None = None, data_tools: Sequence[Tool] = (),
              spend: Any = None, external_meter: Callable[[], float] | None = None,
              default_model: ChatModel | None = None) -> RunResult:
    """Run ``task`` with ``seats`` on a record at ``record`` (a path, or in memory), under ``budget``.
    ``models``: one model for every seat, a mapping by seat name / role / model id, or a function of the seat."""
    if not seats:
        raise ValueError("at least one seat")
    t0 = time.time()
    meter = Meter(budget or Budget(), pricing, external_meter)
    rec = LocalRecord(record, seats, spend=spend)
    inv = rec.start(task.title, task.mission, task.questions, success=task.success, files=task.files)
    model_for = _model_for(models, default_model)
    from . import __version__
    config = {"hypswarm": __version__, "seats": [{"name": s.name, "role": s.role, "model": model_for(s).name}
                                                 for s in seats],
              "budget": {"max_calls": meter.budget.max_calls, "max_usd": meter.budget.max_usd},
              "preamble_sha256": hashlib.sha256(task.preamble().encode()).hexdigest(),
              "data_tools": [t.name for t in data_tools]}
    rid = rec.file_run(inv, config)
    sched = Scheduler(rec, inv, seats, model_for, meter, data_tools=data_tools, preamble=task.preamble())
    try:
        sr = await sched.run()
        rec.finish_run(rid, "succeeded" if sr.stopped == "settled" else "interrupted", sr.stopped)
    except Exception as e:
        rec.finish_run(rid, "failed", f"{type(e).__name__}: {e}")
        raise
    out = RunResult(inv=inv, record_path=rec.g.path, stopped=sr.stopped, report=sr.report,
                    report_accepted=sr.report_accepted, board=rec.question_board(inv), orders=rec.orders(inv),
                    usage=meter.summary(), scheduler=sr, seconds=round(time.time() - t0, 1), run_node=rid)
    log.info("run %s: %s in %d calls, $%.4f", inv, sr.stopped, meter.total.calls, meter.usd)
    return out
