"""
Shared pieces for the examples.

Every example runs for free on scripted models (the default) and for cents on a real provider (``--model``). The
scripted models are honest about what they are: they answer from values the example computed itself, through the
same record tools, the same scheduler and the same refusals a real model meets — so the trace you see is the
record's behaviour, not a mock of it. The one thing they cannot show is a model reasoning badly; for that, run
with ``--model`` and read the refusals.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from hypswarm import Budget, Pricing, RunResult, toolkits
from hypswarm.messages import Tool
from hypswarm.providers.stub import StubModel, calls_made, tool_outputs

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # the record writes arrows; Windows consoles are cp1252


# ── command line ─────────────────────────────────────────────────────────────
def cli(description: str, folder: Path, **extra: Any) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--model", default="", help="provider model id over OPENAI_BASE_URL / OPENAI_API_KEY; omit for scripted models")
    ap.add_argument("--record", default=str(folder / "record.hypgraph"), help="the record file (deleted first with --fresh)")
    ap.add_argument("--budget-calls", type=int, default=120)
    ap.add_argument("--budget-usd", type=float, default=0.50)
    ap.add_argument("--pricing", default="0.2,0.006,0.6", help="$ per million tokens: input,cached,output")
    ap.add_argument("--fresh", action="store_true", help="start from an empty record")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--trace", action="store_true", help="print every tool call and reply, per order")
    for name, kw in extra.items():
        ap.add_argument(f"--{name.replace('_', '-')}", **kw)
    args = ap.parse_args()
    if args.fresh:
        Path(args.record).unlink(missing_ok=True)
    return args


def budget(args: argparse.Namespace) -> Budget:
    return Budget(max_calls=args.budget_calls, max_usd=args.budget_usd)


def pricing(args: argparse.Namespace) -> Pricing:
    a, b, c = (float(x) for x in args.pricing.split(","))
    return Pricing(a, b, c)


def real_model(args: argparse.Namespace) -> Any:
    from hypswarm.providers import OpenAICompatible
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("set OPENAI_API_KEY (and OPENAI_BASE_URL for a non-OpenAI provider) to run with --model")
    return OpenAICompatible(args.model)


def models(args: argparse.Namespace, answers: dict[str, dict[str, Any]]) -> Any:
    """A real model for every seat, or the scripted trio that answers from ``answers``."""
    return real_model(args) if args.model else scripted(answers)


# ── the host's sandbox: a python tool and the instrument's reproducer ───────
def python_sandbox(folder: Path, seconds: int = 60) -> Any:
    """``python(code)`` runs in ``folder`` as a subprocess with a clean environment and a time limit. This is the
    example's sandbox, not a secure one: it is your own machine. Register your own for anything stronger."""
    def run_python(code: str) -> str:
        """Run python 3 in your working folder (the data files are there); print what you need."""
        try:
            p = subprocess.run([sys.executable, "-E", "-s", "-c", code], check=False, cwd=folder, capture_output=True, text=True,
                               timeout=seconds, env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})
        except subprocess.TimeoutExpired:
            return f"error: no output within {seconds} s"
        out = p.stdout + ("\n[stderr]\n" + p.stderr if p.stderr.strip() else "")
        return out[:8000] or "(no output)"
    return run_python


def register_python(folder: Path) -> None:
    fn = python_sandbox(folder)
    toolkits.register("python", lambda ctx: [Tool.from_function(fn, name="python")], "python in the working folder")


def reproducer(folder: Path) -> Any:
    """The instrument: re-runs an author's registered code in the same sandbox and returns its stdout."""
    return python_sandbox(folder)


def stage(folder: Path, files: dict[str, bytes]) -> Path:
    """Write the task's files into a working folder (what a worker's python sees)."""
    work = folder / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    for name, data in files.items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_bytes(data)
    return work


# ── scripted models ──────────────────────────────────────────────────────────
def _target(messages: Any) -> str:
    for m in messages:
        if m.role == "user" and "TARGET" in m.content:
            line = next((ln for ln in m.content.splitlines() if ln.startswith("TARGET")), "")
            parts = line.split()
            return parts[1] if len(parts) > 1 else "?"
    return "?"


def _rework(messages: Any) -> bool:
    return any(m.role == "user" and "Rework of" in m.content for m in messages)


def scripted(answers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Scripted worker / reviewer / lead. ``answers[Q]`` holds what the worker writes for question Q:
    ``values`` (+ ``summary``, ``code``, ``outcome``), ``claim`` and ``scope``; for a knowledge task ``source`` (+ the
    claim that cites it); ``first_try`` = (tool, args) a deliberately wrong first write, so the trace shows the
    refusal the profile adds; ``answer`` = what goes in the report's answers block."""

    def worker(messages: Any, tools: Any) -> Any:
        done, outs = calls_made(messages), tool_outputs(messages)
        if not done:
            time.sleep(1.05)          # the record stamps whole seconds; a scripted model would otherwise write in the order's own second
        q = _target(messages)
        a = answers.get(q)
        if a is None:
            return ("return_work", {"note": f"no scripted answer for {q}"}) if "return_work" not in done else None
        if any("return_work now" in o for o in outs) and "return_work" not in done:
            return ("return_work", {"note": a.get("note", "answered from the files")})
        rework = _rework(messages)
        if "first_try" in a and not done and not rework:
            return a["first_try"]                                   # the deliberately wrong write: the record refuses it
        if "source" in a:                                           # knowledge: the source, then the claim that cites it
            src = next((m.group(1) for o in outs for m in [re.search(r"added (S\d+)", o)] if m), "")
            if not src:
                return ("graph_add", {"type": "source", "fields": a["source"]}) if done.count("graph_add") < 3 else None
            if not any("added CL" in o for o in outs) and done.count("graph_add") < 4:
                return ("graph_add", {"type": "claim", "fields": {"statement": a["claim"], "scope": a["scope"], "kind": "finding"},
                                      "links": [{"rel": "answers", "to": q}, {"rel": "cites", "to": src}]})
            return None
        registered = any(o.startswith("run RUN") for o in outs)     # the honest result went in (a refused first try didn't)
        if a.get("delay_calls", 0) > done.count("find") and not registered:
            return ("find", {"text": q})                            # look around first: lets another seat return before this one
        if "values" in a and not registered and not rework:
            return ("register_run", {"name": a.get("name", f"{q} computation"), "result_summary": f"{q}: {a['summary']}",
                                     "values": a["values"], "code": a.get("code", ""), "outcome": a.get("outcome", ""),
                                     "claim": a["claim"], "answers": q, "scope": a["scope"]})
        if "values" in a and rework:                                # the result is in the record: write the claim from it
            if "find" not in done:
                return ("find", {"type": "result", "text": q})
            found = outs[done.index("find")] if "find" in done else ""
            rs = [c for c, title in re.findall(r"(RS\d+) result — (.*?) —", found) if q in title]
            if rs and "graph_add" not in done:
                return ("graph_add", {"type": "claim", "fields": {"statement": a["claim"], "scope": a["scope"]},
                                      "links": [{"rel": "answers", "to": q}, {"rel": "derived_from", "to": rs[-1]}]})
        return None

    def reviewer(messages: Any, tools: Any) -> Any:
        done, outs = calls_made(messages), tool_outputs(messages)
        if not done:
            time.sleep(1.05)
        if any("return_work now" in o for o in outs) and "return_work" not in done:
            return ("return_work", {"note": "checked against the files and the code"})
        if "review" not in done:
            return ("review", {"node": _target(messages), "verdict": "checked", "method": "Read the result's code and values; the claim says what the result says.",
                               "notes": "Numbers hold; wording stays within the evidence."})
        return None

    def lead(messages: Any, tools: Any) -> Any:
        done, outs = calls_made(messages), tool_outputs(messages)
        if "report_facts" not in done:
            return ("report_facts", {})
        if "submit_report" not in done or (outs and outs[-1].startswith("report refused")):
            facts = next((o for o in outs if o.startswith("## Facts")), "")
            ans = {q: a.get("answer") for q, a in answers.items()}
            return ("submit_report", {"text": facts + "\n\n## Interpretation\n\nThe answers below are the claims the facts "
                                      "list, as the record holds them; nothing beyond the record is asserted.\n\n```answers\n"
                                      + json.dumps(ans) + "\n```"})
        return None

    return {"worker": StubModel(worker, "scripted-worker"), "reviewer": StubModel(reviewer, "scripted-reviewer"),
            "lead": StubModel(lead, "scripted-lead")}


# ── printing the result ──────────────────────────────────────────────────────
def show(res: RunResult, *, quiet: bool = False, trace: bool = False) -> None:
    if trace:
        for w in res.scheduler.workers:
            print(f"\n--- {w.seat} on {w.code}: {w.calls} calls, returned={w.returned} by_record={w.returned_by_record} {w.stopped}")
            for row in w.tool_log:
                print(f"  > {row['tool']}({row['args'][:160]})\n    {row['out'][:400]}")
    print(f"\n=== {res.stopped.upper()} in {res.seconds}s — {res.usage['calls']} calls, ${res.usage['usd']:.4f} ===")
    for q in res.board:
        print(f"  {q['code']:4} {q['status']:12} {q.get('by', '')[:90]}")
    refusals = [(w.seat, w.code, row["out"]) for w in res.scheduler.workers for row in w.tool_log
                if row["out"].startswith("refused") or "refused" in row["out"][:160]]
    if refusals:
        print("\n--- refusals the record issued (and what came back honest) ---")
        for seat, code, out in refusals:
            print(f"  [{seat} on {code}] {out[:300]}")
    events = [e for e in res.scheduler.events if e["kind"] in ("reproduced", "rework", "escalate", "notice", "adopt", "report_missing", "unreviewable")]
    if events:
        print("\n--- scheduler events worth reading ---")
        for e in events:
            print("  " + ", ".join(f"{k}={str(v)[:80]}" for k, v in e.items() if k != "t"))
    if not quiet:
        print("\n--- report ---")
        print(res.report[-2500:] if res.report else "(no report: see report_missing above)")
    print(f"\nrecord: {res.record_path}\n  hypgraph --db {res.record_path} serve        # the Atlas\n"
          f"  hypgraph --db {res.record_path} orders      # every order and its status\n"
          f"  hypgraph --db {res.record_path} refusals    # the refusal log")


def main(coro: Any) -> RunResult:
    return asyncio.run(coro)
