"""
The worker loop. A worker holds no state between orders: its context is the order text and its own turns. It
stops when it returns the order, when the model stops calling tools, or at its turn or budget cap — and if it
stopped without returning, the order is returned on its behalf, so the scheduler always sees a return.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from hypgraph import GraphError

from .budget import BudgetExhausted, Meter
from .messages import Message, Tool
from .providers.base import ChatModel
from .record import Record
from .seats import Seat
from .telemetry import NULL, Telemetry, trace_tools
from .tools import OnWrite, worker_tools

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


CLOSING_REVIEW = ("Two turns are left on this order, and the only tool now is review. Record your verdict on the "
                  "node this order names: checked if it holds as written, objection if it doesn't (say what is wrong), "
                  "inconclusive if the files can't tell. Your method is what you re-ran and compared so far.")


def _closing(seat: Seat, state: dict[str, Any], turns_left: int) -> bool:
    return seat.role == "reviewer" and not state.get("reviewed") and turns_left <= 2


async def run_order(seat: Seat, model: ChatModel, record: Record, inv: str, order: str, *, meter: Meter,
                    data_tools: Sequence[Tool] = (), preamble: str = "", header: str = "",
                    on_write: OnWrite | None = None, tel: Telemetry | None = None, tel_parent: str = "",
                    runs_code: bool = True) -> WorkerResult:
    tel = tel or NULL
    code = record.get(order)["code"]
    res = WorkerResult(order=order, code=code, seat=seat.name)
    rtools = worker_tools(record, seat, inv, order, meter, on_write=on_write, runs_code=runs_code)
    state = rtools[-1].fn.__dict__["_state"]
    tools = trace_tools([t for t in data_tools if seat.may_use(t.name)] + rtools, tel, parent=tel_parent,
                        seat=seat.name, order=code)
    by = {t.name: t for t in tools}
    messages = [Message("system", (header + "\n" if header else "") + seat.prompt()
                        + ("\n\n" + preamble if preamble else "")),
                Message("user", record.order_text(order))]
    closing = False
    for _turn in range(seat.max_turns):
        try:
            meter.reserve(code)                     # the claim on the budget is made before the call, not after
        except BudgetExhausted as e:
            res.stopped = f"budget: {e}"
            break
        offered = tools
        if _closing(seat, state, seat.max_turns - _turn) and "review" in by:
            # A reviewer's order ends on its verdict, not on its turn limit: reviewers re-ran the claim's code turn
            # after turn and the order ran out with no review (studies E6: 1 review in 5 reviewer orders). The last
            # two turns offer only `review` — two, so a refused review gets its retry.
            offered = [by["review"]]
            if not closing:
                messages.append(Message("user", CLOSING_REVIEW))
                closing = True
        t0 = time.time()
        mid = tel.start("model", parent=tel_parent, seat=seat.name, order=code, model=getattr(model, "name", ""),
                        turn=res.turns + 1)
        try:
            reply = await model.complete(messages, offered, temperature=seat.temperature, unit=code)
        except Exception as e:  # noqa: BLE001 — a provider failure ends the order, never the run
            tel.end(mid, ok=False, error=f"{type(e).__name__}: {e}")
            meter.release(code)
            res.stopped = f"error: {type(e).__name__}: {str(e)[:200]}"
            log.warning("worker %s on %s: model error %s", seat.name, code, e)
            break
        meter.add(code, reply.input_tokens, reply.cached_tokens, reply.output_tokens)
        used: dict[str, Any] = {"in": reply.input_tokens, "cached": reply.cached_tokens, "out": reply.output_tokens,
                                "usd": tel.usd(reply.input_tokens, reply.cached_tokens, reply.output_tokens),
                                "tool_calls": [tc.name for tc in reply.tool_calls], "text": tel.text(reply.content)}
        tel.end(mid, **used)
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


async def run_agent_order(seat: Seat, record: Record, inv: str, order: str, *, meter: Meter,
                          data_tools: Sequence[Tool] = (), preamble: str = "", header: str = "",
                          on_write: OnWrite | None = None, tel: Telemetry | None = None,
                          tel_parent: str = "") -> WorkerResult:
    """A seat held by an agent from another framework (``seat.agent``, see hypswarm.agents): it gets the same
    order, prompt and tools a native seat gets, runs its own loop, and reports what it used. One call is reserved
    before it starts (so a run at its budget never starts an agent); the calls it reports are counted when it
    ends, and the order is returned with its note if it did not return it itself."""
    from .agents import AgentOrder, call_agent
    tel = tel or NULL
    code = record.get(order)["code"]
    res = WorkerResult(order=order, code=code, seat=seat.name)
    rtools = worker_tools(record, seat, inv, order, meter, on_write=on_write)
    state = rtools[-1].fn.__dict__["_state"]
    tools = trace_tools([t for t in data_tools if seat.may_use(t.name)] + rtools, tel, parent=tel_parent,
                        seat=seat.name, order=code)
    system = (header + "\n" if header else "") + seat.prompt() + ("\n\n" + preamble if preamble else "")
    try:
        meter.reserve(code)
    except BudgetExhausted as e:
        res.stopped = f"budget: {e}"
    else:
        t0 = time.time()
        ao = AgentOrder(seat=seat, code=code, order=order, text=record.order_text(order), system=system, tools=tools,
                        calls_left=meter.calls_left(), record=record, inv=inv)
        # the framework runs its own loop: its model calls are one span here, with the usage it reports at the end
        mid = tel.start("model", parent=tel_parent, seat=seat.name, order=code, agent=True,
                        model="agent:" + str(getattr(seat.agent, "__name__", type(seat.agent).__name__)))
        try:
            out = await call_agent(seat.agent, ao)
        except Exception as e:  # noqa: BLE001 — a framework failure ends the order, never the run
            tel.end(mid, ok=False, error=f"{type(e).__name__}: {e}")
            meter.release(code)
            res.stopped = f"error: {type(e).__name__}: {str(e)[:200]}"
            log.warning("agent seat %s on %s: %s", seat.name, code, e)
        else:
            n = max(1, out.calls)                   # the reservation becomes the first call; the rest are added
            used: dict[str, Any] = {"in": out.input_tokens, "cached": out.cached_tokens, "out": out.output_tokens,
                                    "calls": n, "usd": tel.usd(out.input_tokens, out.cached_tokens, out.output_tokens)}
            tel.end(mid, **used)
            meter.add(code, out.input_tokens, out.cached_tokens, out.output_tokens)
            for _ in range(n - 1):
                meter.add(code, 0, 0, 0)
            res.calls += n
            res.turns = n
            res.call_log.append({"t": round(t0, 3), "s": round(time.time() - t0, 3), "unit": code, "agent": seat.name,
                                 "in": out.input_tokens, "cached": out.cached_tokens, "out": out.output_tokens,
                                 "calls": n})
            res.tool_log = [{"turn": i + 1, "tool": str(x.get("tool")), "args": _short(x["args"] if isinstance(x.get("args"), dict) else {"_raw": str(x.get("args") or "")}),
                             "out": "", "s": 0.0} for i, x in enumerate(out.log)]
            if state["returned"]:
                res.returned = True
            elif out.note.strip():
                try:
                    c = record.return_work(author=seat.name, order=order, note=out.note[:800])
                    res.returned = True
                    res.tool_log.append({"turn": n, "tool": "return_work", "args": _short({"note": out.note[:120]}),
                                         "out": "returned by the bridge — " + ("every predicate met" if c["all_met"] else "NOT every predicate met"), "s": 0.0})
                except GraphError as e:
                    log.warning("could not return %s for agent seat %s: %s", code, seat.name, e)
    if not state["returned"] and not res.returned:
        try:
            record.return_work(author=seat.name, order=order,
                               note=f"(returned by the record: the agent stopped without returning — {res.stopped or 'no note'})")
            res.returned_by_record = True
        except GraphError as e:
            log.warning("could not return %s on %s's behalf: %s", code, seat.name, e)
    return res


async def await_external(seat: Seat, record: Record, inv: str, order: str, *, timeout_s: float,
                         poll_s: float = 1.0) -> WorkerResult:
    """An external seat works its order through the record (MCP, HTTP, a person): the scheduler only waits for
    the order to leave 'open'. If the lease runs out first, the order is returned on the seat's behalf so the
    scheduler can decide, exactly as for a worker that stopped without returning."""
    code = record.get(order)["code"]
    res = WorkerResult(order=order, code=code, seat=seat.name)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        st = next((o["status"] for o in record.orders(inv) if o["id"] == order), "")
        if st == "returned":
            res.returned = True
            return res
        if st in ("cancelled", "moot", "reworked", "accepted"):
            res.stopped = st
            return res
        await asyncio.sleep(poll_s)
    res.stopped = "lease"
    try:
        record.return_work(author=seat.name, order=order, note="(returned by the record: the lease ran out)")
        res.returned_by_record = True
    except GraphError as e:
        log.warning("could not return %s for external seat %s: %s", code, seat.name, e)
    return res


def _short(args: dict[str, Any]) -> str:
    import json
    return json.dumps(args, ensure_ascii=False, default=str)[:2000]
