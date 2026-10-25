"""
The record tools a seat gets. Every reply ends with what the record did for the writer (numbers it bound, results
it found restated), whether the seat's order is done, and the calls left in the run — the control state, said
where the work happens, so no agent needs a tool call to learn where it stands.
"""

from __future__ import annotations

import json
from typing import Any

from hypgraph import GraphError

from .budget import Meter
from .messages import Tool
from .record import Record
from .seats import Seat


def _tail(n: dict[str, Any], meter: Meter) -> str:
    s = "".join(f"\n  note: {x}" for x in n.get("notes") or [])
    if n.get("restates"):
        s += f"\n  note: this restates {', '.join(n['restates'])}"
    if n.get("orders"):
        s += "\n  your order: " + "; ".join(n["orders"])
    return s + f"\n  (calls left in this run: {meter.calls_left()})"


def _err(e: Exception) -> str:
    return f"refused: {e}"


def worker_tools(record: Record, seat: Seat, inv: str, order: str, meter: Meter) -> list[Tool]:
    """What a worker or reviewer can do to the record while holding an order."""
    me = seat.name
    state = {"returned": False}

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
        if seat.role == "reviewer" and type == "claim":
            return ("refused: you are a reviewer — record a verdict on the claim you were asked to check (review); if "
                    "the right answer is missing, say so in your review notes and return the order, and a worker "
                    "will be asked to write it")
        try:
            n = record.create(author=me, type=type, inv=inv, fields=fields, links=_links(links))
        except (GraphError, KeyError) as e:
            return _err(e)
        return f"added {n['code']} — {n['state']['sentence']}" + _tail(n, meter)

    def register_run(name: str, result_summary: str, values: dict[str, Any] | None = None, outcome: str = "",
                     experiment: str = "", code: str = "", claim: str = "", answers: str = "", scope: str = "",
                     claim_kind: str = "") -> str:
        """Record a computation you ran and the result it produced: values {name: {value, unit} | {k, n}}; code: the
        exact code you ran (the instrument re-executes it, so a reviewer needn't). experiment: the experiment it
        executes, if any. claim (optional): the sentence this result lets you assert — written in the same call,
        derived from the result, its numbers bound to these values; answers: the question code it answers; scope:
        under which conditions it holds. The result counts toward your order by itself; a claim settles a question."""
        try:
            links = [{"rel": "executes", "to": record.resolve(experiment, inv)}] if experiment.strip() else []
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
                return out + f"\n  claim refused: {e}" + _tail(res, meter)
            out += f" → claim {c['code']} — {c['state']['sentence']}"
            return out + _tail(c, meter)
        return out + _tail(res, meter)

    def review(node: str, verdict: str, method: str, notes: str) -> str:
        """Review a claim or result: checked | pass | fail | objection | resolved | inconclusive | comment. Say how
        you checked and what you found. Never your own author's work."""
        try:
            out = record.review(author=me, target=record.resolve(node, inv), verdict=verdict.strip().lower(),
                                method=method, notes=notes)
        except (GraphError, KeyError) as e:
            return _err(e)
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

    tools = [Tool.from_function(f) for f in (graph_add, register_run, review, show, find, return_work)]
    for t in tools:
        t.fn.__dict__["_state"] = state     # the worker loop reads whether return_work ran
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
        tests links [{"rel": "tests", "to": "H1", "data": {"expected": …}}]; or a question {text}."""
        if type not in ("hypothesis", "experiment", "question"):
            return "the lead plans (hypothesis, experiment, question); results and claims come from workers"
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
