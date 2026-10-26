"""
The change suite's runner (P3): every (family, seed) under P (prompted) and R (record), the change fired by the tool
both share, scored against the answers as they are after the change. Writes runs/<stamp>/ with rows.json and a
results.md that reports each prediction of PLAN-CHANGE.md as met / not met.

    python change_run.py --selftest            # generators' truths re-derived, the checker on honest and stale artifacts: $0
    python change_run.py --stub                # every family and seed, both conditions, scripted models: $0
    python change_run.py --model deepseek-ai/DeepSeek-V4.1-Flash --cap-usd 3      # the study (needs approval)

Env for a real run through the pod proxy: OPENAI_BASE_URL, OPENAI_API_KEY, HTTPS_PROXY, SSL_CERT_FILE.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "examples"))

from _common import scripted as scripted_models
from change import CHANGE_FAMILIES, CInstance, check_change, make_change, stub_answers, stub_p_artifact
from pages import PageServer
from ploop import run_p
from run import PRICING, plain_file_tools, python_sandbox_reproducer, python_tool, stage, wilson

from hypswarm import Budget, Task, run, toolkits
from hypswarm.messages import Tool

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Changer:
    """Applies an instance's change once: the files in the work folder, the pages on the local host."""

    def __init__(self, inst: CInstance, work: Path, server: PageServer | None):
        self.inst, self.work, self.server = inst, work, server
        self.fired: dict[str, Any] = {}

    def fire(self, by: str) -> None:
        if self.fired:
            return
        for path, data in self.inst.change.files.items():
            (self.work / path).write_bytes(data)
        if self.server:
            self.server.pages.update(self.inst.change.pages)
        self.fired = {"by": by, "t": round(time.time(), 3)}

    def saw_old_answer(self, out: str) -> bool:
        ev = self.inst.change.evidence
        return not ev or bool(re.search(ev, out or ""))


def changing_python(work: Path, log: list[str], ch: Changer) -> Tool:
    base = python_tool(work, log)

    def python(code: str) -> str:
        """Run python 3 in your working folder (the data files are there; you may write files). Print what you need."""
        out = str(base.fn(code))
        if ch.inst.change.python and re.search(ch.inst.change.python, code) and "Traceback" not in out \
                and ch.saw_old_answer(out):
            ch.fire("python")                               # the old answer was just computed: now the world moves
        return out
    return Tool.from_function(python)


def changing_fetch(server: PageServer, ch: Changer) -> Tool:
    base = server.tool()

    def fetch(url: str) -> str:
        """GET a page on the local source host and return its visible text. Only this host exists; the index lists its pages."""
        out = str(base.fn(url))
        if ch.inst.change.fetch and url.rstrip("/").endswith(ch.inst.change.fetch) and ch.saw_old_answer(out):
            ch.fire("fetch")
        return out
    return Tool.from_function(fetch)


def page_text(server: PageServer):
    """The host's re-fetch for R's world watcher: the page's visible text, as the fetch tool shows it — and it never
    counts as an agent's read, so it can't fire the change."""
    def refetch(url: str) -> str:
        import httpx
        if not url.startswith(server.base):
            raise ValueError("not on the source host")
        r = httpx.get(url, timeout=5)
        if r.status_code != 200:
            raise ValueError(f"HTTP {r.status_code}")
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text)).strip()
    return refetch


def redone(rec_path: Path, inv: str, fired: dict[str, Any]) -> list[str]:
    """Questions whose work was done again after the change: an order issued at or after it that asks for a gate an
    earlier order on the same question already asked for (a rework, a refresh). The next stage of a workflow — a
    review, a position after a backtest — asks for new gates, so it isn't a redo."""
    if not fired:
        return []
    from hypgraph import Graph
    at = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(fired["t"]))
    g = Graph(str(rec_path))
    try:
        rows = []
        for o in g.orders(inv):
            n = g.get(o["id"])
            gates = {str(p.get("p")) for p in n["body"].get("done_when") or []} - {"reviewed", "result_reviewed"}
            q = o.get("target") or ""
            if gates and re.fullmatch(r"Q\d+", q):
                rows.append((n["at"][:19], o["code"], q, gates))
        asked: dict[str, set[str]] = {}
        out = set()
        for when, _code, q, gates in sorted(rows):
            if when >= at and gates & asked.get(q, set()):
                out.add(q)
            asked.setdefault(q, set()).update(gates)
        return sorted(out)
    finally:
        g.close()


def stub_hook(ch: Changer):
    """In the stub nobody calls python: the change fires on the scripted seat's first write from the old state."""
    def on_write(kind: str, payload: dict[str, Any]) -> None:
        c = ch.inst.change
        if kind == "register_run" and c.python and re.search(c.python, str(payload.get("code") or "")):
            ch.fire("write")
        if kind == "graph_add" and payload.get("type") == "source" and c.fetch and \
                str((payload.get("fields") or {}).get("url", "")).rstrip("/").endswith(c.fetch):
            ch.fire("write")
    return on_write


async def run_one(inst: CInstance, cond: str, out: Path, model: Any, *, stub: bool, stale_p: bool = False,
                  max_calls: int = 80, max_usd: float = 0.15) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    work = stage(out, inst)
    log: list[str] = []
    server = PageServer(dict(inst.pages)) if inst.pages else None
    ch = Changer(inst, work, server)
    row: dict[str, Any] = {"family": inst.family, "seed": inst.seed, "cond": cond, "profile": inst.profile,
                           "harmless": inst.harmless, "change": inst.change.what}
    t0 = time.time()
    mission = inst.mission + (f"\n\n{server.index()}" if server else "")
    try:
        if cond == "P":
            tools = plain_file_tools(work) + [changing_python(work, log, ch)] + ([changing_fetch(server, ch)] if server else [])
            if stub:
                ch.fire("stub")
                art = stub_p_artifact(inst, stale_p)
                pres = {"artifact": art, "calls": 1, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "stopped": "stub"}
            else:
                r = await run_p(model, inst.profile, mission, inst.questions, sorted(inst.files), tools, max_calls=max_calls,
                                unit=f"{inst.family}-{inst.seed}-P")
                pres = r.__dict__
            row.update(artifact=pres["artifact"], calls=pres["calls"], stopped=pres["stopped"],
                       usd=PRICING.usd(pres["input_tokens"], pres["cached_tokens"], pres["output_tokens"]))
        else:
            kits = ["files", "python"] + (["fetch"] if server else [])
            toolkits.register("python", lambda ctx: [changing_python(work, log, ch)], "python in the working folder")
            if server:
                toolkits.register("fetch", lambda ctx: [changing_fetch(server, ch)], "the local source host")
            task = Task(title=inst.title, mission=mission, questions=inst.questions, files=inst.files, profile=inst.profile)
            if stub:
                answers = stub_answers(inst)
                for a in answers.values():
                    for part in (a, a.get("after") or {}):
                        if "source" in part:
                            part["source"]["url"] = part["source"]["url"].replace("__BASE__", server.base if server else "")
                models: Any = scripted_models(answers)
            else:
                models = model
            rec_path = out / "record.hypgraph"
            rec_path.unlink(missing_ok=True)
            res = await run(task, None, models, record=rec_path, budget=Budget(max_calls=max_calls, max_usd=max_usd),
                            pricing=PRICING, folder=work, toolkits=kits, reproducer=python_sandbox_reproducer(work),
                            watch=True, refetch=page_text(server) if server else None,
                            on_write=stub_hook(ch) if stub else None)
            ev = res.scheduler.events
            # the locked score counts the lead's report only; an assembled one (the harness, from the current
            # claims) is kept and scored beside it, labelled
            if res.report_source == "assembled":
                row.update(assembled_artifact=res.report, assembled_score=check_change(inst, res.report))
            row.update(artifact=res.report if res.report_accepted else "", report_accepted=res.report_accepted,
                       report_source=res.report_source,
                       calls=res.usage["calls"], usd=res.usage["usd"], stopped=res.stopped,
                       world_changes=res.scheduler.world_changes, reverifications=res.scheduler.reverifications,
                       refreshes=res.scheduler.refreshes,
                       refresh_questions=[e["question"] for e in ev if e["kind"] == "refresh_order"],
                       reverified=[{k: e.get(k) for k in ("result", "confirmed", "contradicted", "supported")}
                                   for e in ev if e["kind"] == "reverified"],
                       board={q["code"]: q["status"] for q in res.board},
                       redo_questions=redone(rec_path, res.inv, ch.fired),
                       # a lost report shows why: the scheduler's report events and the lead's report turns
                       report_events=[e for e in ev if str(e["kind"]).startswith("report")],
                       report_turns=[t for t in res.scheduler.lead_log if t.get("unit") == "report"])
    finally:
        if server:
            server.close()
    row["fired"] = ch.fired
    row["seconds"] = round(time.time() - t0, 1)
    row["score"] = check_change(inst, row.get("artifact") or "")
    (out / "run.json").write_text(json.dumps(row, indent=1, default=str), encoding="utf-8")
    return row


# ── predictions (PLAN-CHANGE.md §4) and the results page ─────────────────────
def results_md(rows: list[dict[str, Any]]) -> str:
    import hashlib
    lock = hashlib.sha256((HERE / "PLAN-CHANGE.md").read_bytes()).hexdigest()
    L = ["# Change suite — results", "", f"_Predictions locked in PLAN-CHANGE.md, sha256 {lock[:16]}…_", "",
         "| family | cond | runs | fired | harmful: current | harmful: STALE shipped | unaffected right | harmless: current | $ | calls | R: questions redone | R: re-verified / supported |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for fam in CHANGE_FAMILIES:
        for cond in ("P", "R"):
            rs = [r for r in rows if r["family"] == fam and r["cond"] == cond]
            if not rs:
                continue
            harm = [r for r in rs if not r["harmless"] and r["fired"]]
            safe = [r for r in rs if r["harmless"] and r["fired"]]
            un = [r for r in rs if r["fired"] and r["score"]["unaffected_ok"] is not None]
            cur = sum(r["score"]["current"] for r in harm)
            st = sum(r["score"]["stale"] for r in harm)
            uok = sum(bool(r["score"]["unaffected_ok"]) for r in un)
            scur = sum(r["score"]["current"] for r in safe)
            refq = [f"{r['seed']}:{q}" for r in rs for q in r.get("redo_questions", [])]
            rv = sum(len(r.get("reverified", [])) for r in rs)
            sup = sum(1 for r in rs for x in r.get("reverified", []) if x.get("supported"))
            L.append(f"| {fam} | {cond} | {len(rs)} | {sum(1 for r in rs if r['fired'])} | {cur}/{len(harm)} | {st}/{len(harm)} | "
                     f"{uok}/{len(un) if un else '—'} | {scur}/{len(safe)} | {sum(r.get('usd', 0) for r in rs):.3f} | "
                     f"{sum(r.get('calls', 0) for r in rs)} | {('%d (%s)' % (len(refq), ','.join(refq))) if cond == 'R' else '—'} | "
                     f"{f'{rv} / {sup}' if cond == 'R' else '—'} |")
    harm = {c: [r for r in rows if r["cond"] == c and not r["harmless"] and r["fired"]] for c in ("P", "R")}
    safe_r = [r for r in rows if r["cond"] == "R" and r["harmless"] and r["fired"]]
    rate = {c: (sum(r["score"]["stale"] for r in harm[c]), len(harm[c])) for c in harm}
    curr = {c: (sum(r["score"]["current"] for r in harm[c]), len(harm[c])) for c in harm}
    lo_p, hi_p = wilson(*rate["P"])
    v = []
    if harm["P"] and harm["R"]:
        pr = rate["P"][0] / rate["P"][1]
        pc, rc = curr["P"][0] / curr["P"][1], curr["R"][0] / curr["R"][1]
        v.append(f"- **1 · P ships stale answers** (≥ 40 %; met when the 95 % lower bound > 15 %): "
                 f"{'MET' if lo_p > 0.15 else 'NOT MET'} — {rate['P'][0]}/{rate['P'][1]} ({pr:.0%}, interval {lo_p:.0%}–{hi_p:.0%})")
        v.append(f"- **2 · R ships no stale answer** (0 %): {'MET' if rate['R'][0] == 0 else 'NOT MET'} — {rate['R'][0]}/{rate['R'][1]}")
        v.append(f"- **3 · R is current more often** (R − P ≥ 20 points on harmful changes): {'MET' if rc - pc >= 0.20 else 'NOT MET'} — "
                 f"R {curr['R'][0]}/{curr['R'][1]} ({rc:.0%}) vs P {curr['P'][0]}/{curr['P'][1]} ({pc:.0%})")
    affected = {(r["family"], r["seed"]): set(make_change(r["family"], r["seed"]).affected) for r in rows if r["cond"] == "R"}
    refs = [(r, q) for r in rows if r["cond"] == "R" and not r["harmless"] for q in r.get("redo_questions", [])]
    on_target = sum(1 for r, q in refs if q in affected[(r["family"], r["seed"])])
    quiet = sum(1 for r in safe_r if not r.get("redo_questions"))
    v.append(f"- **4 · R redoes only what moved** (after a harmful change, no question the change didn't touch is redone; "
             f"after a harmless one, nothing is redone in ≥ 4 of 5 runs): "
             f"{'MET' if on_target == len(refs) and quiet >= max(1, round(0.8 * len(safe_r))) else 'NOT MET'} — "
             f"{on_target}/{len(refs)} redone questions were affected ones; harmless runs with nothing redone {quiet}/{len(safe_r)}")
    cost = {c: sum(r.get("usd", 0) for r in rows if r["cond"] == c) for c in ("P", "R")}
    n = {c: max(1, sum(1 for r in rows if r["cond"] == c)) for c in ("P", "R")}
    good = {c: max(1, sum(1 for r in rows if r["cond"] == c and r["fired"] and r["score"]["current"])) for c in ("P", "R")}
    ratio = (cost["R"] / n["R"]) / (cost["P"] / n["P"]) if cost["P"] else float("nan")
    v.append(f"- **5 · cost** (we predict no cost win: R ≥ 5× P per run): {'MET' if ratio >= 5 else 'NOT MET'} — ratio {ratio:.1f}; "
             f"cost per current artifact P ${cost['P'] / good['P']:.4f} vs R ${cost['R'] / good['R']:.4f}")
    nf = [f"{r['family']}-{r['seed']}-{r['cond']}" for r in rows if not r["fired"]]
    L += ["", "## Predictions (PLAN-CHANGE.md §4)", ""] + v
    L += ["", f"Runs where the change never fired (the old answer was never computed by a tool; excluded above): {', '.join(nf) or 'none'}"]
    return "\n".join(L) + "\n"


# ── self-test ────────────────────────────────────────────────────────────────
def selftest() -> int:
    """The generators' truths re-derived independently, and the checker on honest and stale artifacts. $0."""
    bad = 0
    for fam in CHANGE_FAMILIES:
        for seed in range(5):
            inst = make_change(fam, seed)
            honest, stale = check_change(inst, stub_p_artifact(inst)), check_change(inst, stub_p_artifact(inst, True))
            ok = honest["current"] and not honest["stale"] and honest["unaffected_ok"] is not False
            ok_s = inst.harmless or (stale["stale"] and not stale["current"])
            note = ""
            if fam == "C2":                                  # run the real tests on both trees
                for tree, want in (("pre", inst.pre["Q2"]["passed"]), ("post", inst.post["Q2"]["passed"])):
                    d = HERE / "runs" / "selftest-change" / f"C2-{seed}-{tree}"
                    shutil.rmtree(d, ignore_errors=True)
                    for p, data in inst.files.items():
                        (d / p).parent.mkdir(parents=True, exist_ok=True)
                        (d / p).write_bytes(data)
                    if tree == "post":
                        for p, data in inst.change.files.items():
                            (d / p).write_bytes(data)
                    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=d, capture_output=True, text=True, timeout=120)
                    m = re.search(r"(\d+) passed", r.stdout)
                    got = int(m.group(1)) if m else 0
                    if got != want:
                        ok = False
                        note += f" {tree}: pytest {got} passed, truth says {want}"
            bad += (not ok) + (not ok_s)
            print(f"{fam} seed {seed}{' harmless' if inst.harmless else ''}: honest {'OK' if ok else 'FAIL'} | "
                  f"stale {'OK' if ok_s else 'FAIL'}{note}")
    print("selftest:", "PASS" if not bad else f"{bad} FAILURES")
    return bad


async def main() -> None:
    ap = argparse.ArgumentParser(description="the change suite (P3)")
    ap.add_argument("--families", default=",".join(CHANGE_FAMILIES))
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--seed-from", type=int, default=0)
    ap.add_argument("--conditions", default="P,R")
    ap.add_argument("--model", default="")
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--stale-p", action="store_true", help="stub only: P writes the pre-change answers (exercises the checker)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--merge", nargs="*", default=None, help="lane folders under runs/ to combine into --out")
    ap.add_argument("--rescore", action="store_true",
                    help="with --merge: score every row's stored artifact again with the current checker")
    ap.add_argument("--cap-usd", type=float, default=3.0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if args.selftest:
        raise SystemExit(selftest())
    if args.merge is not None:
        rows = []
        for lane in args.merge:
            f = HERE / "runs" / lane / "rows.json"
            if f.exists():
                rows += json.loads(f.read_text(encoding="utf-8"))
        root = HERE / "runs" / (args.out or "change-merged")
        root.mkdir(parents=True, exist_ok=True)
        rows.sort(key=lambda r: (r["family"], r["seed"], r["cond"]))
        if args.rescore:                        # deterministic: the stored artifact, the instance, the checker
            for r in rows:
                old = r["score"]
                r["score"] = check_change(make_change(r["family"], r["seed"]), r.get("artifact") or "")
                if {k: old.get(k) for k in ("current", "stale", "unaffected_ok")} != \
                        {k: r["score"].get(k) for k in ("current", "stale", "unaffected_ok")}:
                    print(f"rescored {r['family']}-{r['seed']}-{r['cond']}: {old} -> {r['score']}")
        (root / "rows.json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
        (root / "results.md").write_text(results_md(rows), encoding="utf-8")
        print(f"merged {len(rows)} rows into {root / 'results.md'}; spent ${sum(r.get('usd', 0) for r in rows):.3f}")
        return
    if not args.stub and not args.model:
        raise SystemExit("--model <id> for a real run, or --stub")
    model: Any = None
    if not args.stub:
        from hypswarm.providers import OpenAICompatible
        model = OpenAICompatible(args.model, timeout_s=120)
    stamp = args.out or time.strftime("%Y%m%d-%H%M") + ("-change-stub" if args.stub else "-change")
    root = HERE / "runs" / stamp
    rows, spent = [], 0.0
    for fam in args.families.split(","):
        for seed in range(args.seed_from, args.seeds):
            inst = make_change(fam, seed)
            for cond in args.conditions.split(","):
                if spent >= args.cap_usd:
                    print(f"cap ${args.cap_usd} reached; stopping")
                    break
                row = await run_one(inst, cond, root / f"{fam}-{seed}-{cond}", model, stub=args.stub, stale_p=args.stale_p)
                spent += row.get("usd", 0)
                rows.append(row)
                s = row["score"]
                print(f"{fam}-{seed}-{cond}{' harmless' if inst.harmless else ''}: {row.get('stopped')} calls={row.get('calls')} "
                      f"${row.get('usd', 0):.4f} fired={bool(row['fired'])} current={s['current']} stale={s['stale']} "
                      f"unaffected_ok={s['unaffected_ok']}"
                      + (f" refreshes={row.get('refresh_questions')} reverified={len(row.get('reverified', []))}" if cond == "R" else ""),
                      flush=True)
    root.mkdir(parents=True, exist_ok=True)
    (root / "rows.json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    (root / "results.md").write_text(results_md(rows), encoding="utf-8")
    print(f"\n{root / 'results.md'}\nspent ${spent:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
