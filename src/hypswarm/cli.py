"""
    hypswarm run --task task.toml --seats seats.toml --record study.hypgraph [--budget-calls 150 --budget-usd 2]
    hypswarm run --task task.toml --seats seats.toml --record-url http://127.0.0.1:8765   # hypgraph serve --writable
    hypswarm status --record study.hypgraph
    hypswarm report --record study.hypgraph

task.toml:
    title = "Does A beat B"
    mission = "…"
    files = ["items.csv"]                     # copied into the record as artifacts (hashes); workers read them
    [[questions]]
    code = "Q1"
    text = "What is model A's accuracy?"

seats.toml:
    [[seats]]
    name = "analyst"
    role = "worker"                           # worker | reviewer | lead
    model = "deepseek-ai/DeepSeek-V4.1-Flash"  # provider model id (OPENAI_BASE_URL / OPENAI_API_KEY)
    takes = ["accuracy", "counts", "question"]
    [[seats]]
    name = "nicolas"
    role = "worker"
    external = true                           # a person (or another agent) takes its orders over MCP:
                                              #   hypgraph --db study.hypgraph --as nicolas mcp  → my_work

The CLI uses the OpenAI-compatible provider; the Python API takes any ChatModel.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from . import __version__
from .budget import Budget, Pricing
from .run import Task, run
from .seats import Seat


def _load_task(path: str) -> Task:
    d = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    files = {Path(p).name: Path(p).read_bytes() for p in d.get("files", [])}
    return Task(title=d["title"], mission=d["mission"],
                questions=[(q["code"], q["text"], q.get("asks", "")) for q in d["questions"]],
                files=files, success=d.get("success", ""), notes=d.get("notes", ""), profile=d.get("profile", ""))


def _load_seats(path: str) -> list[Seat]:
    d = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return [Seat(name=s["name"], role=s.get("role", "worker"), model=s.get("model", ""), takes=tuple(s.get("takes", [])),
                 about=s.get("about", ""), temperature=s.get("temperature"), max_turns=int(s.get("max_turns", 14)),
                 external=bool(s.get("external", False)))
            for s in d["seats"]]


def cmd_run(a: argparse.Namespace) -> int:
    from .providers.openai_compat import OpenAICompatible
    task = _load_task(a.task)
    if a.profile:
        task = Task(**{**task.__dict__, "profile": a.profile})
    seats = _load_seats(a.seats) if a.seats else None      # None: the profile's roster
    if seats is None and not task.profile:
        raise SystemExit("give --seats, or a task/--profile whose roster to use")
    default = a.model or os.environ.get("HYPSWARM_MODEL", "")
    cache: dict[str, OpenAICompatible] = {}

    for s in seats or []:
        if s.external:
            print(f"seat {s.name} is external — take it with:\n  {s.mcp_hint(a.record or ':memory:')}", file=sys.stderr)
    if any(s.external for s in (seats or [])) and not a.record:
        raise SystemExit("external seats need --record (a file both sides can open)")

    def model_for(seat: Seat) -> OpenAICompatible:
        mid = seat.model or default
        if not mid:
            raise SystemExit(f"seat {seat.name}: no model (set model= in seats.toml, --model or HYPSWARM_MODEL)")
        if mid not in cache:
            cache[mid] = OpenAICompatible(mid, base_url=a.base_url, timeout_s=a.timeout)
        return cache[mid]
    pricing = Pricing(*map(float, a.pricing.split(","))) if a.pricing else None
    budget = Budget(max_calls=a.budget_calls, max_usd=a.budget_usd)
    record: Any = a.record
    if a.record_url:
        from .http_record import HttpRecord
        record = HttpRecord(a.record_url)
    r = asyncio.run(run(task, seats, model_for, record=record, budget=budget, pricing=pricing,
                        folder=a.folder or None))
    print(r.report)
    print(f"\n--- {r.stopped} · {r.usage['calls']} calls · ${r.usage['usd']:.4f} · {r.seconds}s · record {r.record_path}",
          file=sys.stderr)
    return 0 if r.stopped == "settled" else 1


def cmd_profiles(a: argparse.Namespace) -> int:
    from .profiles import PROFILES, names
    for pid in names():
        sp = PROFILES[pid]
        seats = ", ".join(f"{s.name} ({s.role})" for s in sp.seats)
        kits = ", ".join(sp.toolkits) or "-"
        print(f"{pid}: {sp.about}\n  seats: {seats}\n  toolkits: {kits}")
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    from hypgraph import Graph
    g = Graph(a.record)
    for i in g.investigations():
        print(f"{i['code']} {i['title']}")
        for q in g.question_board(i["id"]):
            print(f"  {q['code']} {q['status'].upper():<11} {q['text'][:80]}" + (f" — {q['by']}" if q["by"] else ""))
        for o in g.orders(i["id"]):
            print(f"  {o['code']:<5} {o['status']:<9} {o['assignee']:<12} {o['target']:<6} {o['objective'][:60]}")
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    from hypgraph import Graph
    g = Graph(a.record)
    for i in g.investigations():
        print(g.report(i["id"])["markdown"])
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="hypswarm", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"hypswarm {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a task with seats on a record")
    r.add_argument("--task", required=True)
    r.add_argument("--seats", default="", help="seats.toml; omit to use the profile's roster")
    r.add_argument("--profile", default="", help="scientific | software | trading | knowledge | optimization")
    r.add_argument("--folder", default="", help="working folder for the files toolkit")
    r.add_argument("--record", default="")
    r.add_argument("--record-url", default="", help="a record served by `hypgraph serve --writable`")
    r.add_argument("--model", default="", help="default model id for seats without one")
    r.add_argument("--base-url", default="", help="OpenAI-compatible endpoint (default OPENAI_BASE_URL)")
    r.add_argument("--timeout", type=float, default=180.0)
    r.add_argument("--budget-calls", type=int, default=150)
    r.add_argument("--budget-usd", type=float, default=0.0)
    r.add_argument("--pricing", default="", help="input,cached,output $ per million tokens")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("status", help="the question board and orders of a record")
    s.add_argument("--record", required=True)
    s.set_defaults(fn=cmd_status)
    rp = sub.add_parser("report", help="the facts of each investigation, from the record")
    rp.add_argument("--record", required=True)
    rp.set_defaults(fn=cmd_report)
    pf = sub.add_parser("profiles", help="the governance profiles and their rosters")
    pf.set_defaults(fn=cmd_profiles)
    a = p.parse_args(argv)
    return int(a.fn(a))


if __name__ == "__main__":
    sys.exit(main())
