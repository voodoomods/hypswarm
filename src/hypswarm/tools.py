"""
The record tools a seat gets. Every reply ends with what the record did for the writer (numbers it bound, results
it found restated), whether the seat's order is done, and the calls left in the run — the control state, said
where the work happens, so no agent needs a tool call to learn where it stands.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from hypgraph import GraphError

from .budget import Meter
from .messages import Tool
from .record import Record
from .seats import Seat

log = logging.getLogger("hypswarm.tools")


def _tail(n: dict[str, Any], meter: Meter) -> str:
    s = "".join(f"\n  note: {x}" for x in n.get("notes") or [])
    if n.get("restates"):
        s += f"\n  note: this restates {', '.join(n['restates'])}"
    if n.get("orders"):
        s += "\n  your order: " + "; ".join(n["orders"])
    return s + f"\n  (calls left in this run: {meter.calls_left()})"


def _err(e: Exception) -> str:
    return f"refused: {e}"


OnWrite = Callable[[str, dict[str, Any]], None]


def _live(n: dict[str, Any]) -> bool:
    st = n.get("state") or {}
    return (st.get("lifecycle") or "active") == "active" and not st.get("fallen")


_TIME_UNIT = re.compile(r"^(?:s|secs?|seconds?|ms|msecs?|milliseconds?|us|µs|μs|microseconds?|ns|nanoseconds?)$",
                        re.IGNORECASE)
# The code measures time: only then is a value in seconds a timing. A duration that is the data (parse_duration("2.6s")
# returns 3 seconds) re-runs to the same digits; it was refused as a timing (studies E4, evening run).
_MEASURES_TIME = re.compile(r"\b(?:perf_counter(?:_ns)?|monotonic(?:_ns)?|process_time(?:_ns)?|thread_time(?:_ns)?|"
                            r"time_ns|timeit|default_timer|time\.time|datetime\.now|utcnow)\b")
_TIME_KEY = re.compile(r"(?:_|^)(?:s|sec|secs|seconds|ms|us|ns)$|(?:^|_)(?:time|timing|elapsed|duration|latency)(?:_|$)",
                       re.IGNORECASE)


_METHOD_MAX = 1500                     # a review's method, as the record's schema caps it


def _timings_without_spread(values: dict[str, Any]) -> list[str]:
    """Values that are timings (a time unit, or a key such as median_slow_s / elapsed_ms) and carry no spread."""
    out = []
    for k, v in values.items():
        if isinstance(v, dict):
            if "spread" in v or "rel_tol" in v or "k" in v or not isinstance(v.get("value"), (int, float)):
                continue
            unit = str(v.get("unit") or "").strip()
            if _TIME_UNIT.match(unit) or (not unit and _TIME_KEY.search(k)):
                out.append(k)
        elif isinstance(v, (int, float)) and not isinstance(v, bool) and _TIME_KEY.search(k):
            out.append(k)
    return out


def implied_uses(record: Record, inv: str, order: str, code: str) -> list[str]:
    """The artifacts a registered run used, as far as the record can tell without the author saying so: every live
    file artifact whose path the code names, and — under a workflow — the live diff or instance that is part of the
    order's question (the tests you ran while holding the order ran on the current head). Freshness then works
    without the model remembering to declare ``uses``."""
    out: list[str] = []
    if code.strip():
        for a in record.search("", "artifact", inv, 500):
            n = record.get(a["id"])
            b = n.get("body") or {}
            path = str(b.get("path") or "")
            if not path or path == "." or "://" in path or b.get("kind") == "excerpt" or not _live(n):
                continue
            names = {path, path.rsplit("/", 1)[-1]}
            if any(re.search(r"(?<![\w.-])" + re.escape(x) + r"(?![\w.-])", code) for x in names):
                out.append(a["id"])
    try:
        target = next((e["dst"] for e in record.get(order).get("out", []) if e.get("rel") == "works_on"), "")
        if target and record.get(target)["type"] == "question":
            for e in record.get(target).get("in", []):
                if e.get("rel") != "part_of":
                    continue
                n = record.get(e["src"])
                if n["type"] == "artifact" and (n.get("body") or {}).get("kind") in ("diff", "instance") and _live(n):
                    out.append(n["id"])
    except (GraphError, KeyError):
        pass
    return list(dict.fromkeys(out))


_CODE = re.compile(r"\b(?:Q|T|CL|RS|RUN|RV|H|X|D)\d+\b")


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def _not_a_question(text: str, existing: list[tuple[str, str]]) -> str:
    """Why a lead's question isn't one ('' = it is). Leads added orders as questions — "Q2 claim: the analyst's T10
    must write, on the existing run result RS5 …?" — and copies of open questions, and each owed the whole workflow
    (studies S2, S3, E6 day 2: every one of the three runs grew a Q4)."""
    codes = _CODE.findall(text)
    if codes:
        return (f"refused: a question asks what the run must find out about the world; this one names record entries "
                f"({', '.join(dict.fromkeys(codes))}). To send that work to a seat, rework its order (rework) with "
                "done_when")
    mine = _words(text)
    for code, other in existing:
        theirs = _words(other)
        # a copy, or a copy with a clause added ("… or decline — given the honest out-of-sample result …": the
        # added words diluted the overlap below 0.8, and the run owed Q3 twice; studies T2, evening)
        if mine and theirs and (len(mine & theirs) / len(mine | theirs) >= 0.8 or len(mine & theirs) / len(theirs) >= 0.9):
            return (f"refused: {code} already asks this. To get it answered, rework the order on {code} (rework) — "
                    "a second copy owes the whole workflow again")
    return ""


def worker_tools(record: Record, seat: Seat, inv: str, order: str, meter: Meter,
                 on_write: OnWrite | None = None, runs_code: bool = True) -> list[Tool]:
    """What a worker or reviewer can do to the record while holding an order. ``on_write(kind, payload)`` is told
    after every accepted ``graph_add`` / ``register_run`` (a host's hook; it never changes the reply).
    ``runs_code=False``: nothing the seat holds executes code, so ``register_run`` refuses code — it can't have run.
    Through the CLI with only the files toolkit, seats registered code with its "output" 14 times in one run; with no
    instrument nothing checked it, and code text counts as the code behind a result (studies O1, evening)."""
    me = seat.name
    state = {"returned": False, "reviewed": False}

    def _told(kind: str, payload: dict[str, Any]) -> None:
        if on_write:
            try:
                on_write(kind, payload)
            except Exception as e:  # noqa: BLE001 — a host hook never costs a worker its write
                log.warning("on_write hook failed on %s: %s", kind, e)

    def _links(links: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        out = []
        for l in links or []:
            d = dict(l)
            for k in ("to", "from"):
                if d.get(k):
                    d[k] = record.resolve(str(d[k]), inv)
            out.append(d)
        return out

    def graph_add(type: str, fields: dict[str, Any], links: list[dict[str, Any]] | None = None) -> str:
        """Add to the record. result {summary, outcome, values: {name: {value, unit} | {k, n}}} · claim
        {statement, scope, kind, measurements: [{name, result, key, k, n | value}]} · hypothesis {statement,
        predictions[]} · experiment {aim, protocol, success_criteria}. links: [{"rel": "answers", "to": "Q1"},
        {"rel": "derived_from", "to": "RS1"}, {"rel": "supports", "to": "H1", "why": …}]. A claim's numbers are
        bound to your own results when the record can find them; a refused claim says exactly what to fix.
        A reviewer writes reviews, not claims: a claim by the only reviewer could never be reviewed."""
        if type == "artifact" and (fields or {}).get("kind") == "diff":
            arts = [record.get(a["id"]) for a in record.search("", "artifact", inv, 500)]
            heads = [a for a in arts if (a.get("body") or {}).get("format") == "tree" and _live(a)]
            if heads:
                # the watcher owns the head: a seat's own diff made a second line of heads, one of them an empty
                # file registered mid-write, and the tests never ran on "the current head" (studies/challenges E1)
                return (f"refused: the record watches the working tree — {heads[-1].get('code', 'its head')} is the "
                        "current head, and an edit to the files registers the next one. Edit the files; don't "
                        "register a diff")
        if seat.role == "reviewer" and type == "claim":
            return ("refused: you are a reviewer — record a verdict on the claim you were asked to check (review); if "
                    "the right answer is missing, say so in your review notes and return the order, and a worker "
                    "will be asked to write it")
        try:
            n = record.create(author=me, type=type, inv=inv, fields=fields, links=_links(links))
        except (GraphError, KeyError) as e:
            return _err(e)
        _told("graph_add", {"type": type, "fields": fields, "code": n["code"], "id": n["id"]})
        return f"added {n['code']} — {n['state']['sentence']}" + _tail(n, meter)

    def graph_link(src: str, rel: str, dst: str, why: str = "") -> str:
        """Link two nodes you can see: part_of (an artifact or source → a question), uses (a run → an artifact),
        supports / challenges (why required), supersedes (a newer diff or instance → the old one)."""
        try:
            record.link(author=me, src=record.resolve(src, inv), rel=rel, dst=record.resolve(dst, inv), why=why)
        except (GraphError, KeyError) as e:
            return _err(e)
        return f"linked {src} -{rel}-> {dst}"

    def register_run(name: str, result_summary: str, values: dict[str, Any] | None = None, outcome: str = "",
                     experiment: str = "", code: str = "", claim: str = "", answers: str = "", scope: str = "",
                     claim_kind: str = "", uses: list[str] | None = None) -> str:
        """Record a computation you ran and the result it produced: values {name: {value, unit} | {k, n}} — a value
        that varies run to run (a timing, an unseeded sample) also takes its spread: {value, unit, spread: [lo, hi]}
        or rel_tol (a fraction), and the instrument confirms a re-run inside it; code: the
        exact code you ran — the instrument re-executes it and checks that the output shows every value you register,
        so PRINT each registered value with its name (print("n_items", n_items)). experiment: the experiment it
        executes, if any. uses: artifact codes the run read — the diff it tested, the instance it solved, the data
        file (a workflow reads 'tests on the current head' and freshness off these). claim (optional): the sentence
        this result lets you assert — written in the same call, derived from the result, its numbers bound to these
        values; answers: the question code it answers; scope: under which conditions it holds; claim_kind: finding
        (default) | exclusion | inconclusive. The result counts toward your order by itself; a claim settles a
        question."""
        if code.strip() and not runs_code:
            return ("refused: nothing in this run executes code, so this code wasn't run and isn't evidence. Register "
                    "only what you read off the files (values, no code), or return the order and say it needs a tool "
                    "that runs code")
        bare = _timings_without_spread(values or {}) if _MEASURES_TIME.search(code) else []
        if bare and code.strip():
            # the instrument re-runs the code: a re-timed value never lands on the same digits, and every timing
            # registered bare came back CONTRADICTED while the ones with a spread were confirmed (studies E2)
            return (f"refused: {', '.join(bare)} {'is a timing' if len(bare) == 1 else 'are timings'} — a re-run "
                    "never prints the same digits, so the instrument would contradict it. Give each its spread over "
                    "your repeats: {value, unit, spread: [lo, hi]} or rel_tol (a fraction)")
        try:
            links: list[dict[str, Any]] = [{"rel": "executes", "to": record.resolve(experiment, inv)}] if experiment.strip() else []
            declared = [record.resolve(str(a), inv) for a in (uses or []) if str(a).strip()]
            links += [{"rel": "uses", "to": a, "data": {"role": "data"}}
                      for a in dict.fromkeys(declared + implied_uses(record, inv, order, code))]
            rfields: dict[str, Any] = {"kind": "agent", "name": name[:300], "state": "succeeded", "note": code[:1500]}
            if code.strip():
                rfields["config"] = {"source": code[:18000], "language": "python"}
            r = record.create(author=me, type="run", inv=inv, links=links, fields=rfields)
            rf: dict[str, Any] = {"summary": result_summary, "values": values or {}, "kind": "computed"}
            if outcome:
                rf["outcome"] = outcome
            res = record.create(author=me, type="result", inv=inv, fields=rf,
                                links=[{"rel": "produced", "from": r["id"]}])
        except (GraphError, KeyError) as e:
            return _err(e)
        _told("register_run", {"code": code, "values": values or {}, "result": res["code"], "run": r["code"]})
        out = f"run {r['code']} → result {res['code']}"
        if claim.strip():
            cf: dict[str, Any] = {"statement": claim, "scope": scope or result_summary}
            if claim_kind:
                cf["kind"] = claim_kind
            cl_links: list[dict[str, Any]] = [{"rel": "derived_from", "to": res["id"]},
                                              {"rel": "supports", "from": res["id"],
                                               "why": "the result this claim's numbers come from"}]
            if answers.strip():
                try:
                    cl_links.append({"rel": "answers", "to": record.resolve(answers, inv)})
                except (GraphError, KeyError) as e:
                    return out + f"\n  claim not written: {e}" + _tail(res, meter)
            try:
                c = record.create(author=me, type="claim", inv=inv, fields=cf, links=cl_links)
            except (GraphError, KeyError) as e:
                why = str(e)
                if why.startswith("claim refused:"):      # the record's own prefix; don't say it twice
                    why = why[len("claim refused:"):].strip()
                return out + f"\n  claim refused: {why}" + _tail(res, meter)
            out += f" → claim {c['code']} — {c['state']['sentence']}"
            return out + _tail(c, meter)
        return out + _tail(res, meter)

    def review(node: str, verdict: str, method: str, notes: str) -> str:
        """Review a claim or result: checked | pass | fail | objection | resolved | inconclusive | comment. Say how
        you checked and what you found. Never your own author's work."""
        if len(method) > _METHOD_MAX:
            # a thorough method over the record's limit lost the whole review (studies E3): the rest goes in notes
            cut = method.rfind(" ", 0, _METHOD_MAX - 40)
            cut = cut if cut > 0 else _METHOD_MAX - 40
            method, notes = (method[:cut] + " … (continued in notes)",
                             f"Method, continued: {method[cut:].strip()}\n\n{notes}"[:4000])
        try:
            out = record.review(author=me, target=record.resolve(node, inv), verdict=verdict.strip().lower(),
                                method=method, notes=notes)
        except (GraphError, KeyError) as e:
            return _err(e)
        state["reviewed"] = True
        return f"{out['code']}: {out['state']['sentence']}" + _tail(out, meter)

    def show(node: str) -> str:
        """A node's fields, standing and links."""
        try:
            n = record.get(record.resolve(node, inv))
        except (GraphError, KeyError) as e:
            return _err(e)
        return json.dumps({"code": n["code"], "type": n["type"], "standing": n["state"]["sentence"], "body": n["body"],
                           "links": [f"{e['rel']} {record.get(e['dst'])['code']}" for e in n["out"]]},
                          default=str)[:6000]

    def find(text: str = "", type: str = "") -> str:
        """Nodes in this investigation matching words and/or a type."""
        rows = record.search(text, type, inv, 30)
        return str("\n".join(f"{r['code']} {r['type']} — {r['title'][:100]} — {r['state']['sentence'][:80]}"
                             for r in rows) or "nothing matches")

    def return_work(note: str = "") -> str:
        """Hand your order back with a note of at most 120 words: what you did, what you could not."""
        try:
            c = record.return_work(author=me, order=order, note=note)
        except (GraphError, KeyError) as e:
            return _err(e)
        state["returned"] = True
        return "returned — " + ("every predicate met" if c["all_met"] else "NOT every predicate met: "
                                                                        + "; ".join(x["why"] for x in c["predicates"] if not x["met"]))

    tools = [Tool.from_function(f) for f in (graph_add, graph_link, register_run, review, show, find, return_work)]
    for t in tools:
        t.fn.__dict__["_state"] = state     # the worker loop reads whether return_work / review ran
    return tools


def lead_tools(record: Record, seat: Seat, inv: str, meter: Meter, *, report_box: dict[str, Any],
               roster: list[dict[str, str]], order_author: str = "") -> list[Tool]:
    """What the lead can do at an exception and for the report: plan, re-plan, judge; never the workers' work.
    ``order_author``: the author that issued the orders (the scheduler), so the lead's rework and cancel act on
    them — only an order's author may withdraw it."""
    me = seat.name
    oa = order_author or me
    seq = {"n": 0}

    def briefing() -> str:
        """Your context, compiled from the record: the question board, exceptions, orders in flight and returned."""
        b = record.briefing(inv, roster=roster, since_seq=seq["n"])
        seq["n"] = b["seq"]
        return str(b["text"]) + f"\n(calls left in this run: {meter.calls_left()})"

    def add(type: str, fields: dict[str, Any], links: list[dict[str, Any]] | None = None) -> str:
        """Plan: a hypothesis {statement, predictions[]} or an experiment {aim, protocol, success_criteria} with
        tests links [{"rel": "tests", "to": "H1", "data": {"expected": …}}]; or a question {text, asks?: "measure"}
        (asks=measure when it wants a number or a check of what exists: no change, hypothesis or backtest)."""
        if type not in ("hypothesis", "experiment", "question"):
            return "the lead plans (hypothesis, experiment, question); results and claims come from workers"
        if type == "question" and "?" not in str((fields or {}).get("text") or ""):
            # a lead once added "Assign it to risk as a REVIEW of CL2 …" as a question, and the run then owed it a
            # whole trading workflow (studies/challenges T1 Q4)
            return ("refused: a question asks what the run must find out, ending with '?'. To send work to a seat, "
                    "rework its order (rework) with done_when; a question owes the whole workflow")
        if type == "question":
            why = _not_a_question(str((fields or {}).get("text") or ""),
                                  [(q.get("code") or "", str((q.get("body") or {}).get("text") or ""))
                                   for q in (record.get(x["id"]) for x in record.search("", "question", inv, 200))])
            if why:
                return why
        try:
            ls = [dict(l, to=record.resolve(str(l["to"]), inv)) if l.get("to") else l for l in (links or [])]
            n = record.create(author=me, type=type, inv=inv, fields=fields, links=ls)
        except (GraphError, KeyError) as e:
            return _err(e)
        return f"added {n['code']}"

    def rework(order: str, missing: str, done_when: list[Any] | None = None) -> str:
        """Send an order back as a new order to the same worker, saying what was missing; done_when changes the
        predicates (a stuck predicate must change)."""
        try:
            r = record.rework(author=oa, order=record.resolve(order, inv), missing=missing, done_when=done_when)
        except (GraphError, KeyError) as e:
            return _err(e)
        return f"reworked as {r['code']}"

    def cancel_work(order: str, why: str) -> str:
        """Cancel an order, with the reason."""
        try:
            record.cancel_work(author=oa, order=record.resolve(order, inv), why=f"{me}: {why}")
        except (GraphError, KeyError) as e:
            return _err(e)
        return f"{order} cancelled"

    def report_facts() -> str:
        """The facts of the investigation generated from the record. Start the report from them."""
        return str(record.report(inv)["markdown"])

    def submit_report(text: str) -> str:
        """Submit the final report: the facts plus your interpretation. It is checked against the record; errors
        come back to fix."""
        r = record.check_text(text, inv)
        errs = [f for f in r["findings"] if f["level"] == "error"]
        if errs:
            report_box["refusals"] = int(report_box.get("refusals", 0)) + 1
            report_box.setdefault("refused", []).append([f"{f['code']}: {f['excerpt'][:100]}" for f in errs[:6]])
            return "report refused: " + "; ".join(f"line {f['line']} {f['code']}: {f['excerpt'][:100]}"
                                                  for f in errs[:6]) + " — fix these and submit again"
        report_box["text"] = text
        return "report accepted"

    def show(node: str) -> str:
        """A node's fields, standing and links."""
        try:
            n = record.get(record.resolve(node, inv))
        except (GraphError, KeyError) as e:
            return _err(e)
        return json.dumps({"code": n["code"], "type": n["type"], "standing": n["state"]["sentence"], "body": n["body"]},
                          default=str)[:6000]

    return [Tool.from_function(f) for f in (briefing, add, rework, cancel_work, report_facts, submit_report, show)]
