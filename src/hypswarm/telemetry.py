"""Telemetry: what a run does that the record can't see — every model call, tool call, work order and scheduler
decision, as spans — for live observability (HypGraph's Live view) and for your own tracing stack.

    run(task, seats, model, record="desk.hypgraph")              # → desk.hypgraph.telemetry.jsonl beside the record
    run(..., telemetry="path/to/run.telemetry.jsonl")             # somewhere else
    run(..., telemetry=False)                                      # off
    run(..., otel=True)                                            # also OpenTelemetry spans and metrics (hypswarm[otel])
    run(..., capture_content=True)                                 # include prompts' replies, tool arguments and outputs

The record stays the source of truth; telemetry is observation and is never trusted for standing. Each event is one
JSON line:

    {"v": 1, "ts": 1793055418.702, "at": "2026-10-26T22:49:03.702Z", "run": "<run node>", "inv": "<inv id>",
     "kind": "model_end", "span": "s-…", "parent": "s-…", "seat": "analyst", "order": "T3", …fields}

kinds: run_start · run_end · order_start · order_end · model_start · model_end · tool_start · tool_end · decision.
Spans nest run → order → model / tool. ``model_end`` carries tokens in / cached / out, $ (at the run's pricing), the
model, seconds, ok / error and the tool calls it asked for; ``tool_end`` carries seconds, ok / error and the output's
size. By default no prompt, reply text, tool argument value or output is written: arguments are summarised as their
names and value types, and anything secret-looking is scrubbed. ``capture_content=True`` adds them (truncated, still
scrubbed).
"""

from __future__ import annotations

import inspect
import json
import re
import threading
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .messages import Tool

V = 1
_SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|nvapi-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{12,}|xox[abp]-[A-Za-z0-9-]{10,}|"
                     r"AKIA[0-9A-Z]{12,}|Bearer\s+[A-Za-z0-9._~+/=-]{8,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+|"
                     r"(?i:(?:api[_-]?key|token|secret|password|passwd)\s*[=:]\s*)\S+)")
_SECRET_KEY = re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|authorization|credential)")


def scrub(text: str) -> str:
    """Secret-looking strings replaced — over-scrubbing is preferred to leaking."""
    return _SECRET.sub("***", text)


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts)) + f".{int((ts % 1) * 1000):03d}Z"


class JsonlSink:
    """Appends one JSON line per event to a file, flushed as written (a reader tailing it sees each event at once)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("a", encoding="utf-8")
        self._lock = threading.Lock()

    def __call__(self, ev: dict[str, Any]) -> None:
        line = json.dumps(ev, ensure_ascii=False, default=str)
        with self._lock:
            self._f.write(line + "\n")
            self._f.flush()

    def close(self) -> None:
        with self._lock:
            self._f.close()


class OtelSink:
    """OpenTelemetry: each start/end pair becomes a span (run → order → model / tool, with gen_ai.* attributes), and
    model calls feed counters for calls, tokens and $. Uses the OpenTelemetry API only: the tracer and meter
    providers are whatever your process configured (an OTLP exporter to Datadog, Grafana, Honeycomb …); with none
    configured it is a no-op. ``pip install 'hypswarm[otel]'``."""

    def __init__(self, tracer_provider: Any = None, meter_provider: Any = None):
        from opentelemetry import metrics, trace
        self._trace = trace
        self._tracer = (tracer_provider or trace.get_tracer_provider()).get_tracer("hypswarm")
        m = (meter_provider or metrics.get_meter_provider()).get_meter("hypswarm")
        self._calls = m.create_counter("hypswarm.model.calls", unit="{call}", description="model calls")
        self._tokens = m.create_counter("gen_ai.client.token.usage", unit="{token}", description="tokens used")
        self._usd = m.create_counter("hypswarm.model.cost", unit="USD", description="model spend at the run's pricing")
        self._tools = m.create_counter("hypswarm.tool.calls", unit="{call}", description="tool calls")
        self._open: dict[str, Any] = {}
        self._lock = threading.Lock()

    def __call__(self, ev: dict[str, Any]) -> None:
        kind = str(ev.get("kind") or "")
        attrs = {f"hypswarm.{k}": v for k, v in ev.items() if k in ("run", "inv", "seat", "order") and v}
        if kind.endswith("_start"):
            what = kind[:-6]
            name = {"model": f"chat {ev.get('model') or ''}".strip(), "tool": f"execute_tool {ev.get('tool') or ''}".strip(),
                    "order": f"order {ev.get('order') or ''}".strip(), "run": "hypswarm.run"}.get(what, what)
            if what == "model":
                attrs.update({"gen_ai.operation.name": "chat", "gen_ai.request.model": str(ev.get("model") or "")})
            if what == "tool":
                attrs.update({"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": str(ev.get("tool") or "")})
            with self._lock:
                parent = self._open.get(str(ev.get("parent") or ""))
            ctx = self._trace.set_span_in_context(parent) if parent is not None else None
            span = self._tracer.start_span(name, context=ctx, attributes=attrs, start_time=int(ev["ts"] * 1e9))
            with self._lock:
                self._open[str(ev["span"])] = span
        elif kind.endswith("_end"):
            with self._lock:
                span = self._open.pop(str(ev.get("span") or ""), None)
            if span is None:
                return
            if kind == "model_end":
                span.set_attributes({"gen_ai.usage.input_tokens": int(ev.get("in") or 0),
                                     "gen_ai.usage.output_tokens": int(ev.get("out") or 0),
                                     "hypswarm.cached_tokens": int(ev.get("cached") or 0), "hypswarm.usd": float(ev.get("usd") or 0)})
                labels = {"gen_ai.request.model": str(ev.get("model") or ""), "hypswarm.seat": str(ev.get("seat") or "")}
                self._calls.add(1, labels)
                self._tokens.add(int(ev.get("in") or 0), labels | {"gen_ai.token.type": "input"})
                self._tokens.add(int(ev.get("out") or 0), labels | {"gen_ai.token.type": "output"})
                self._usd.add(float(ev.get("usd") or 0), labels)
            if kind == "tool_end":
                self._tools.add(1, {"gen_ai.tool.name": str(ev.get("tool") or ""), "hypswarm.ok": bool(ev.get("ok", True))})
            if not ev.get("ok", True):
                from opentelemetry.trace import Status, StatusCode
                span.set_status(Status(StatusCode.ERROR, str(ev.get("error") or "")[:200]))
            span.end(end_time=int(ev["ts"] * 1e9))
        else:
            with self._lock:
                parent = self._open.get(str(ev.get("parent") or "")) or self._open.get(str(ev.get("run") or ""))
            if parent is not None:
                parent.add_event(kind if kind != "decision" else f"decision {ev.get('event', '')}",
                                 {k: str(v)[:200] for k, v in ev.items() if k not in ("v", "ts", "at", "kind", "span", "parent")})

    def close(self) -> None:
        with self._lock:
            spans, self._open = list(self._open.values()), {}
        for s in spans:                                   # a run that ended abruptly still closes its spans
            s.end()


class Telemetry:
    """Emits events to its sinks. Spans: ``start(kind, …)`` returns a span id and writes ``<kind>_start``;
    ``end(span, …)`` writes ``<kind>_end`` with the seconds it took. With no sinks every call is a cheap no-op."""

    def __init__(self, sinks: Sequence[Any] = (), *, run: str = "", inv: str = "", capture_content: bool = False,
                 pricing: Any = None):
        self.sinks = list(sinks)
        self.run, self.inv, self.capture, self.pricing = run, inv, capture_content, pricing
        self._open: dict[str, tuple[str, float, dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self.on = bool(self.sinks)

    def emit(self, kind: str, *, span: str = "", parent: str = "", **fields: Any) -> dict[str, Any]:
        if not self.on:
            return {}
        ts = time.time()
        ev = {"v": V, "ts": round(ts, 3), "at": _iso(ts), "run": self.run, "inv": self.inv, "kind": kind}
        if span:
            ev["span"] = span
        if parent:
            ev["parent"] = parent
        ev.update({k: v for k, v in fields.items() if v is not None})
        for s in self.sinks:
            try:
                s(ev)
            except Exception:  # noqa: BLE001, S110 — a broken sink never breaks a run
                pass
        return ev

    def start(self, kind: str, *, parent: str = "", span: str = "", **fields: Any) -> str:
        if not self.on:
            return ""
        sid = span or "s-" + uuid.uuid4().hex[:12]
        keep = {k: fields[k] for k in ("seat", "order", "model", "tool") if fields.get(k)}
        with self._lock:
            self._open[sid] = (kind, time.time(), keep | ({"parent": parent} if parent else {}))
        self.emit(f"{kind}_start", span=sid, parent=parent, **fields)
        return sid

    def end(self, sid: str, *, ok: bool = True, error: str = "", **fields: Any) -> None:
        if not self.on or not sid:
            return
        with self._lock:
            kind, t0, keep = self._open.pop(sid, ("span", time.time(), {}))
        parent = keep.pop("parent", "")
        self.emit(f"{kind}_end", span=sid, parent=parent, **keep, s=round(time.time() - t0, 3), ok=ok,
                  error=scrub(error)[:300] if error else None, **fields)

    def usd(self, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
        try:
            return round(float(self.pricing.usd(input_tokens, cached_tokens, output_tokens)), 9) if self.pricing else 0.0
        except Exception:  # noqa: BLE001
            return 0.0

    def args(self, args: dict[str, Any]) -> dict[str, Any]:
        """A tool call's arguments as telemetry may carry them: names and value types by default, values (truncated,
        scrubbed) with capture_content; a secret-looking name is never written with its value."""
        out: dict[str, Any] = {}
        for k, v in (args or {}).items():
            if _SECRET_KEY.search(str(k)):
                out[k] = "***"
            elif self.capture:
                out[k] = scrub(v if isinstance(v, str) else json.dumps(v, default=str))[:600]
            else:
                out[k] = type(v).__name__ if not isinstance(v, str) else f"str[{len(v)}]"
        return out

    def text(self, s: str, n: int = 2000) -> str | None:
        return scrub(s)[:n] if self.capture and s else None

    def close(self) -> None:
        with self._lock:
            left = list(self._open)
        for sid in left:                                  # spans a crash left open are closed, marked not ok
            self.end(sid, ok=False, error="ended without closing (the run stopped)")
        for s in self.sinks:
            close = getattr(s, "close", None)
            if close:
                try:
                    close()
                except Exception:  # noqa: BLE001, S110 — closing a sink never breaks a run
                    pass


NULL = Telemetry()


def trace_tools(tools: Sequence[Tool], tel: Telemetry, *, parent: str = "", seat: str = "", order: str = "") -> list[Tool]:
    """The same tools, each call a ``tool`` span under ``parent``. The span is captured here, not read from the call's
    context, so tools a framework runs on its own thread or event loop are traced too."""
    if not tel.on:
        return list(tools)
    out = []
    for t in tools:
        async def traced(_t: Tool = t, **kw: Any) -> str:
            sid = tel.start("tool", parent=parent, seat=seat, order=order, tool=_t.name, args=tel.args(kw))
            try:
                res = await _t.call(kw)
            except Exception as e:
                tel.end(sid, ok=False, error=f"{type(e).__name__}: {e}")
                raise
            text = res if isinstance(res, str) else json.dumps(res, default=str)
            bad = text.startswith(("error", "refused")) or " refused:" in text[:200]
            tel.end(sid, ok=not bad, error=text[:200] if bad else "", out_chars=len(text), out=tel.text(text))
            return text
        try:                                              # frameworks read the real signature (args_schema, defaults)
            traced.__signature__ = inspect.signature(t.fn)  # type: ignore[attr-defined]
        except (TypeError, ValueError):
            pass
        traced.__name__, traced.__doc__ = getattr(t.fn, "__name__", t.name), getattr(t.fn, "__doc__", t.description)
        out.append(Tool(name=t.name, description=t.description, parameters=t.parameters, fn=traced))
    return out


def build(telemetry: Any, *, record: Any, run: str, inv: str, otel: bool, capture_content: bool, pricing: Any) -> Telemetry:
    """The run's Telemetry from run()'s arguments: ``telemetry`` = "auto" (a sidecar beside a record file), a path, a
    Telemetry, or False / None (off); ``otel`` adds OpenTelemetry."""
    if isinstance(telemetry, Telemetry):
        telemetry.run, telemetry.inv = telemetry.run or run, telemetry.inv or inv
        return telemetry
    sinks: list[Any] = []
    path: Path | None = None
    if telemetry == "auto":
        if isinstance(record, (str, Path)) and str(record) not in ("", ":memory:"):
            path = Path(str(record) + ".telemetry.jsonl")
    elif telemetry:
        path = Path(str(telemetry))
    if path:
        sinks.append(JsonlSink(path))
    if otel:
        sinks.append(OtelSink())
    return Telemetry(sinks, run=run, inv=inv, capture_content=capture_content, pricing=pricing)


__all__ = ["NULL", "JsonlSink", "OtelSink", "Telemetry", "build", "scrub", "trace_tools"]
