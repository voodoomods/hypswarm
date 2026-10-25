"""
The worker loop. A worker holds no state between orders: its context is the order text and its own turns. It
stops when it returns the order, when the model stops calling tools, or at its turn or budget cap — and if it
stopped without returning, the order is returned on its behalf, so the scheduler always sees a return.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from hypgraph import GraphError

from .budget import BudgetExhausted, Meter
from .messages import Message, Tool
from .providers.base import ChatModel
from .record import Record
from .seats import Seat
from .tools import worker_tools

log = logging.getLogger("hypswarm.worker")


@dataclass
class WorkerResult:
    order: str
    code: str
    seat: str
    calls: int = 0
    turns: int = 0
    returned: bool = False
    returned_by_record: bool = False
    stopped: str = ""                       # "" | "turns" | "budget" | "error"
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    call_log: list[dict[str, Any]] = field(default_factory=list)   # one row per model call: t, s, in, cached, out


async def run_order(seat: Seat, model: ChatModel, record: Record, inv: str, order: str, *, meter: Meter,
                    data_tools: Sequence[Tool] = (), preamble: str = "") -> WorkerResult:
    code = record.get(order)["code"]
    res = WorkerResult(order=order, code=code, seat=seat.name)
    rtools = worker_tools(record, seat, inv, order, meter)
    state = rtools[-1].fn.__dict__["_state"]
    tools = [t for t in data_tools if seat.may_use(t.name)] + rtools
    by = {t.name: t for t in tools}
    messages = [Message("system", seat.prompt() + ("\n\n" + preamble if preamble else "")),
                Message("user", record.order_text(order))]
    for _turn in range(seat.max_turns):
        try:
            meter.check(code)
        except BudgetExhausted as e:
            res.stopped = f"budget: {e}"
            break
        t0 = time.time()
        try:
            reply = await model.complete(messages, tools, temperature=seat.temperature, unit=code)
        except Exception as e:  # noqa: BLE001 — a provider failure ends the order, never the run
            res.stopped = f"error: {type(e).__name__}: {str(e)[:200]}"
            log.warning("worker %s on %s: model error %s", seat.name, code, e)
            break
        meter.add(code, reply.input_tokens, reply.cached_tokens, reply.output_tokens)
        res.calls += 1
        res.turns += 1
        res.call_log.append({"t": round(t0, 3), "s": round(time.time() - t0, 3), "unit": code, "agent": seat.name,
                             "in": reply.input_tokens, "cached": reply.cached_tokens, "out": reply.output_tokens})
        messages.append(reply.as_message())
        if not reply.tool_calls:
            break
        for tc in reply.tool_calls:
            tool = by.get(tc.name)
            out = await tool.call(tc.args) if tool else f"error: there is no tool {tc.name!r}"
            res.tool_log.append({"turn": res.turns, "tool": tc.name, "args": _short(tc.args), "out": out[:1500],
                                 "s": round(time.time() - t0, 2)})
            messages.append(Message("tool", out[:12000], tool_call_id=tc.id))
        if state["returned"]:
            res.returned = True
            break
    else:
        res.stopped = res.stopped or "turns"
    if not state["returned"]:
        try:
            record.return_work(author=seat.name, order=order,
                               note=f"(returned by the record: the worker stopped without returning — {res.stopped or 'no tool call'})")
            res.returned_by_record = True
        except GraphError as e:
            log.warning("could not return %s on %s's behalf: %s", code, seat.name, e)
    return res


def _short(args: dict[str, Any]) -> str:
    import json
    return json.dumps(args, ensure_ascii=False, default=str)[:2000]
