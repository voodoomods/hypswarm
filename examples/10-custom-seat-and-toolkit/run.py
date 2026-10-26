"""
10 · Your own seat and your own toolkit, from scratch.

Two extension points and nothing else:

  toolkits.register(name, factory)   a bundle of tools the host provides, built per run over a ToolContext
  Seat(..., agent=fn)                a seat held by any code you write: fn(AgentOrder) -> AgentOutcome | str | None

Here the toolkit is `csvstats` (column statistics over the working folder, read-only) and the seat is a 40-line
agent with no model at all: it reads the order, calls the toolkit, registers the result and claim through the
record's tools, and returns when the record says the order is done. The record treats it exactly like a seat held
by a frontier model: same orders, same refusals, same instrument re-run.

    python run.py
"""
from __future__ import annotations

import csv
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import budget, cli, main, pricing, scripted, show, stage

from hypswarm import AgentOrder, AgentOutcome, Seat, Task, run, toolkits
from hypswarm.messages import Tool
from hypswarm.toolkits import ToolContext

HERE = Path(__file__).resolve().parent
DATA = ("day,temp_c\n" + "\n".join(f"{d},{18 + 6 * ((d * 7) % 11) / 10:.1f}" for d in range(60)) + "\n").encode()


# ── 1. a toolkit: a factory over the run's working folder ────────────────────
def csvstats_factory(ctx: ToolContext) -> list[Tool]:
    folder = ctx.folder or Path(".")

    def column_stats(file: str, column: str) -> dict:
        """Mean, median, min, max and n of a numeric column of a CSV in your working folder."""
        p = (folder / file).resolve()
        if folder.resolve() not in p.parents:
            return {"error": "outside the working folder"}
        v = [float(r[column]) for r in csv.DictReader(p.open(encoding="utf-8")) if r.get(column) not in (None, "")]
        return {"n": len(v), "mean": round(statistics.fmean(v), 3), "median": round(statistics.median(v), 3), "min": min(v), "max": max(v)}
    return [Tool.from_function(column_stats)]


toolkits.register("csvstats", csvstats_factory, "mean / median / min / max of a CSV column")


# ── 2. a seat: an agent function; no model, just code ────────────────────────
async def stats_agent(order: AgentOrder) -> AgentOutcome:
    """Reads the order's target, computes with the toolkit, writes result + claim, returns when done."""
    tool = {t.name: t for t in order.tools}
    q = next((ln.split()[1] for ln in order.text.splitlines() if ln.startswith("TARGET")), "")
    m = re.search(r"'(\w+)' .*? of (\w+\.csv)", order.text)
    if not m:
        return "the order's target names no column and file I can read"
    column, file = m.group(1), m.group(2)
    st = await tool["column_stats"].call({"file": file, "column": column})
    import json
    st = json.loads(st)
    out = await tool["register_run"].call({
        "name": f"{column} statistics", "result_summary": f"{q}: column_stats on {file}.{column}.",
        "values": {"mean": {"value": st["mean"], "unit": "°C"}, "n": {"value": st["n"]}},
        "code": f"import csv, statistics\nv = [float(r['{column}']) for r in csv.DictReader(open('{file}'))]\nprint('mean', round(statistics.fmean(v), 3)); print('n', len(v))",
        "claim": f"The mean of '{column}' in {file} is {st['mean']} °C.", "answers": q, "scope": f"{file}, {st['n']} daily values."})
    log = [{"tool": "column_stats", "args": {"file": file, "column": column}}, {"tool": "register_run", "args": {"answers": q}}]
    if "return_work now" in out:
        await tool["return_work"].call({"note": f"mean of {column} computed with csvstats; claim written"})
        log.append({"tool": "return_work", "args": {}})
    return AgentOutcome(note="done", calls=0, log=log)          # no model was called: the budget counts the reservation only


if __name__ == "__main__":
    args = cli("10 · a custom seat and toolkit", HERE)
    work = stage(HERE, {"weather.csv": DATA})
    # scientific@1: the frozen pre-workflow profile (the example is about a custom seat); 01 runs the workflow (scientific@2)
    task = Task(title="Mean temperature", profile="scientific@1",
                mission="weather.csv holds 60 daily temperatures (day,temp_c). Report the mean.",
                questions=[("Q1", "What is the mean of 'temp_c' in the 60 rows of weather.csv?")], files={"weather.csv": DATA})
    mean = round(statistics.fmean(18 + 6 * ((d * 7) % 11) / 10 for d in range(60)), 3)
    seats = [Seat("stats", "worker", agent=stats_agent, tools=("column_stats", "list_files", "read_file")),
             Seat("critic", "reviewer"), Seat("lead", "lead")]
    models = scripted({"Q1": {"answer": mean}})                 # the critic and lead stay scripted; the worker is your code
    res = main(run(task, seats, models, record=args.record, budget=budget(args), pricing=pricing(args),
                   folder=work, toolkits=["files", "csvstats"]))
    show(res, quiet=args.quiet, trace=args.trace)
