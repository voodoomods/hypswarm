"""Telemetry (telemetry.py): every model call, tool call, work order and scheduler decision of a run, as spans in a
JSONL sidecar beside the record (what HypGraph's Live view streams) and optionally OpenTelemetry. Prompts, replies,
tool argument values and outputs stay out unless capture_content is on, and secrets are scrubbed either way."""
import asyncio
import collections
import inspect
import json

import pytest

from hypswarm import Budget, Pricing, run
from hypswarm.messages import Tool
from hypswarm.telemetry import Telemetry, scrub, trace_tools

from .test_alpha import SEATS, TASK, make_models


def _events(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def _run(tmp_path, **kw):
    return asyncio.run(run(TASK, SEATS, make_models(), record=tmp_path / "t.hypgraph", budget=Budget(max_calls=60),
                           pricing=Pricing(0.2, 0.006, 0.6), **kw))


def test_a_run_writes_a_complete_sidecar_beside_its_record(tmp_path):
    res = _run(tmp_path)
    side = tmp_path / "t.hypgraph.telemetry.jsonl"
    assert res.telemetry == str(side) and side.exists()
    evs = _events(side)
    kinds = collections.Counter(e["kind"] for e in evs)
    assert kinds["run_start"] == kinds["run_end"] == 1 and kinds["order_start"] == kinds["order_end"] >= 2
    assert kinds["model_end"] == res.usage["calls"]                      # one span per metered model call
    assert kinds["tool_start"] == kinds["tool_end"] >= 1 and kinds["decision"] >= 1
    starts = {e["span"]: e for e in evs if e["kind"].endswith("_start")}
    assert {e["span"] for e in evs if e["kind"].endswith("_end")} == set(starts)        # every span closes
    assert all(e["parent"] in starts for e in evs if e.get("parent"))   # and nests: run → order → model / tool
    run_start = next(e for e in evs if e["kind"] == "run_start")
    assert run_start["run"] == res.run_node and run_start["inv"] == res.inv and run_start["budget"]["max_calls"] == 60
    orders = {e["span"] for e in evs if e["kind"] == "order_start"}
    worker_calls = [e for e in evs if e["kind"] == "model_end" and e["seat"] != "lead"]
    assert worker_calls and all(e["parent"] in orders and e["order"].startswith("T") for e in worker_calls)
    m = worker_calls[0]
    assert m["in"] > 0 and m["out"] > 0 and m["usd"] > 0 and m["ok"] and "tool_calls" in m and m["s"] >= 0
    end = next(e for e in evs if e["kind"] == "run_end")
    assert end["stopped"] == res.stopped and end["calls"] == res.usage["calls"]
    assert abs(end["usd"] - res.usage["usd"]) < 1e-6
    assert all(e["v"] == 1 and e["ts"] and e["at"].endswith("Z") for e in evs)
    # content is off by default: no reply text, no tool argument values, no outputs
    assert not any("text" in e or "out" in e and e["kind"] == "tool_end" for e in evs)
    assert all(all(isinstance(v, str) and (v.startswith("str[") or v in ("dict", "list", "int", "float", "bool", "NoneType", "***"))
                   for v in e["args"].values()) for e in evs if e["kind"] == "tool_start")


def test_capture_content_adds_text_and_values_still_scrubbed(tmp_path):
    _run(tmp_path, capture_content=True)
    evs = _events(tmp_path / "t.hypgraph.telemetry.jsonl")
    starts = [e for e in evs if e["kind"] == "tool_start"]
    assert any(any(not v.startswith("str[") for v in e["args"].values()) for e in starts)    # values now present
    assert any(e.get("out") for e in evs if e["kind"] == "tool_end")


def test_off_and_in_memory_write_nothing(tmp_path):
    assert _run(tmp_path, telemetry=False).telemetry == ""
    assert not (tmp_path / "t.hypgraph.telemetry.jsonl").exists()
    res = asyncio.run(run(TASK, SEATS, make_models(), record=None, budget=Budget(max_calls=60)))
    assert res.telemetry == ""
    other = tmp_path / "elsewhere" / "run.jsonl"
    assert _run(tmp_path, telemetry=other).telemetry == str(other) and other.exists()


def test_secrets_are_scrubbed_and_secret_named_arguments_never_written():
    assert scrub("key sk-abcdefghijklmnop and Bearer abc.def.ghi123") == "key *** and ***"
    assert "hunter2" not in scrub("password=hunter2")
    t = Telemetry([lambda e: None], capture_content=True)
    a = t.args({"api_key": "sk-live-1234567890", "query": "Authorization: Bearer xyz123456789", "n": 3})
    assert a["api_key"] == "***" and "xyz123456789" not in a["query"] and a["n"] == "3"


def test_traced_tools_keep_their_signature_and_report_failures():
    seen = []

    def lookup(code: str, depth: int = 1) -> str:
        """Look a node up."""
        return "error: no such node" if code == "X9" else f"{code}@{depth}"

    tel = Telemetry([seen.append])
    [t] = trace_tools([Tool.from_function(lookup)], tel, parent="s-p", seat="analyst", order="T1")
    assert list(inspect.signature(t.fn).parameters) == ["code", "depth"] and t.fn.__doc__ == "Look a node up."
    assert asyncio.run(t.call({"code": "Q1", "depth": 2})) == "Q1@2"
    assert asyncio.run(t.call({"code": "X9"})).startswith("error")
    ends = [e for e in seen if e["kind"] == "tool_end"]
    assert [e["ok"] for e in ends] == [True, False] and ends[1]["error"].startswith("error")
    assert all(e["parent"] == "s-p" and e["seat"] == "analyst" and e["order"] == "T1" for e in seen)


def test_a_broken_sink_never_breaks_a_run(tmp_path):
    def bad(_e):
        raise OSError("disk full")
    res = _run(tmp_path, telemetry=Telemetry([bad]))
    assert res.stopped == "settled"


def test_opentelemetry_spans_nest_and_carry_gen_ai_attributes(tmp_path, monkeypatch):
    pytest.importorskip("opentelemetry.sdk")
    # CI sets OTEL_SDK_DISABLED (to keep CrewAI's own telemetry quiet), and the SDK honours it with no-op tracers — as
    # it should for users. This test is about our spans, so it turns the SDK back on for its own providers.
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from hypswarm.telemetry import OtelSink
    exp, reader = InMemorySpanExporter(), InMemoryMetricReader()
    tp = TracerProvider()
    tp.add_span_processor(SimpleSpanProcessor(exp))
    sink = OtelSink(tracer_provider=tp, meter_provider=MeterProvider(metric_readers=[reader]))
    seen: list = []
    res = _run(tmp_path, telemetry=Telemetry([sink, seen.append], pricing=Pricing(0.2, 0.006, 0.6)))
    spans = exp.get_finished_spans()
    by = collections.Counter(s.name.split(" ")[0] for s in spans)
    why = (f"spans {dict(by)}; events the sink saw {collections.Counter(e['kind'] for e in seen)}; "
           f"tracer {type(sink._tracer).__name__}")             # if this fails again, it says where the spans went
    assert by["hypswarm.run"] == 1 and by["order"] >= 2 and by["chat"] == res.usage["calls"] and by["execute_tool"] >= 1, why
    root = next(s for s in spans if s.name == "hypswarm.run")
    chat = next(s for s in spans if s.name.startswith("chat") and s.attributes.get("hypswarm.seat") != "lead")
    order = next(s for s in spans if s.context.span_id == chat.parent.span_id)
    assert order.name.startswith("order") and order.parent.span_id == root.context.span_id
    assert chat.attributes["gen_ai.usage.input_tokens"] > 0 and chat.attributes["gen_ai.request.model"]
    names = {m.name for rm in reader.get_metrics_data().resource_metrics for sm in rm.scope_metrics for m in sm.metrics}
    assert {"hypswarm.model.calls", "gen_ai.client.token.usage", "hypswarm.model.cost"} <= names
