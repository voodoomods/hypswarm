"""
The instrument re-executes what authors registered, so reviewers judge instead of recomputing.

In the harmony confirmatory the reviewer seat spent 28–47 model calls a run re-deriving every number with its own
python — half of every record run's cost. The numbers were already in the record, next to the code that produced
them. Re-running that code is mechanical: no model is needed to do it, and the result belongs to the instrument,
not to the author or the reviewer. The scheduler calls a host-supplied ``reproducer(source) -> stdout`` for every
result whose run carries its source, checks that each registered value appears in the output, and files a lab run
that ``replicates`` the author's run with the outcome. The review order then says "reproduced — judge the method
and the wording"; a failed reproduction says so, and the reviewer knows where to look.

The host decides how code runs (the same sandbox its workers use, a lab, a container). hypswarm never executes
anything itself.
"""

from __future__ import annotations

import inspect
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from .record import INSTRUMENT, Record

Reproducer = Callable[[str], "str | Awaitable[str]"]
log = logging.getLogger("hypswarm.reproduce")

_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _numbers(text: str) -> list[float]:
    out = []
    for m in _NUM.findall(text):
        try:
            out.append(float(m))
        except ValueError:
            continue
    return out


def _matches(value: float, printed: list[float]) -> bool:
    """A registered value appears in the output at its own precision (or as a percentage of a fraction)."""
    s = repr(value)
    dec = len(s.split(".")[1]) if "." in s and "e" not in s else 0
    for p in printed:
        if round(p, dec) == round(value, dec):
            return True
        if 0 <= value <= 1 and round(p, max(0, dec - 2)) == round(value * 100, max(0, dec - 2)):
            return True
    return False


def _num(x: object) -> bool:
    """A registered number: int or float, not a bool, not the text a seat sometimes writes ("40/50")."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _labelled(name: str, stdout: str) -> list[float]:
    """Numbers the output prints next to this value's own name ('n_items: 1352', 'n_items = 1352', 'n_items 1352')."""
    pat = re.compile(re.escape(name) + r"\s*[:=]?\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", re.IGNORECASE)
    out = []
    for m in pat.finditer(stdout):
        try:
            out.append(float(m.group(1)))
        except ValueError:
            continue
    return out


def _spread(v: Any) -> tuple[float, float] | None:
    """The range a measured value may move in on a re-run, as its author stated it: ``spread`` [lo, hi] or ``rel_tol``
    (a fraction of the value). For a count {k, n} the range applies to k. None when the author stated neither."""
    if not isinstance(v, dict):
        return None
    centre = v.get("k") if "k" in v and "n" in v else v.get("value")
    sp = v.get("spread")
    if isinstance(sp, (list, tuple)) and len(sp) == 2 and all(isinstance(x, (int, float)) for x in sp):
        return float(min(sp)), float(max(sp))
    tol = v.get("rel_tol")
    if isinstance(tol, (int, float)) and isinstance(centre, (int, float)) and tol >= 0:
        return float(centre) - abs(float(centre)) * float(tol), float(centre) + abs(float(centre)) * float(tol)
    return None


def check_output(values: dict[str, Any], stdout: str) -> dict[str, Any]:
    """What the re-run's output says about each registered value, kept apart because they mean different things:

    confirmed    the value appears in the output (at its own precision, or as a percentage)
    unprinted    the code computed it but printed nothing matching — not evidence against; the author should print
                 what they register (E′, 2026-10-25: 116 of 258 'not reproduced' were this, and a false negative
                 sent reviewers recomputing more than before)
    contradicted the output prints a *different* number next to this value's name
    within       a measured value (a timing, a sampled count) whose author stated its ``spread`` or ``rel_tol``: the
                 re-run printed, next to its name, a number inside that range. Counted as confirmed, and named apart
                 so a reader can tell "the same number" from "within its stated spread" (studies E2: every timing
                 was contradicted for differing in the third digit, and the run never settled)

    ``ok`` is true when nothing is contradicted and at least one value is confirmed. Only the program's own output
    counts: a ``[stderr]`` section (as a host sandbox appends it) never confirms a value, and a traceback means the
    re-run failed — nothing is confirmed and ``error`` says why (a "line 1" in a traceback once confirmed a
    registered value of 1)."""
    out_part, _, err_part = stdout.partition("\n[stderr]\n")
    failed = "Traceback (most recent call last)" in err_part or stdout.lstrip().startswith("Traceback (most recent call last)")
    if failed:
        names = [n for n, v in (values or {}).items() if isinstance(v, (dict, int, float))]
        last = (err_part or stdout).strip().splitlines()[-1][:200] if (err_part or stdout).strip() else "the re-run raised"
        return {"confirmed": [], "unprinted": names, "contradicted": [], "found": [], "missing": names, "ok": False,
                "error": last}
    printed = _numbers(out_part)
    confirmed: list[str] = []
    unprinted: list[str] = []
    contradicted: list[str] = []
    within: list[str] = []
    for name, v in (values or {}).items():
        want: list[float] = []
        if isinstance(v, dict):
            if _num(v.get("k")) and _num(v.get("n")):
                want = [float(v["k"]), float(v["n"])]
            elif _num(v.get("value")):
                want = [float(v["value"])]
        elif _num(v):
            want = [float(v)]
        if not want:
            continue
        labelled = _labelled(name, out_part)
        rng = _spread(v)
        if all(_matches(w, printed) for w in want):
            confirmed.append(name)
        elif rng and any(rng[0] <= x <= rng[1] for x in labelled) and \
                ("n" not in v or _matches(float(v["n"]), printed)):          # a count's n must still be the same
            confirmed.append(name)
            within.append(name)
        elif labelled and any(_matches(want[0], [x]) for x in labelled):
            # printed next to its name exactly; a count's denominator just wasn't printed ("n_tutored 80" for
            # {k: 80, n: 600}) — confirmed, not contradicted (studies S2: three right counts flagged CONTRADICTED)
            confirmed.append(name)
        elif labelled:
            contradicted.append(name)
        else:
            unprinted.append(name)
    return {"confirmed": confirmed, "unprinted": unprinted, "contradicted": contradicted, "within": within,
            "found": confirmed, "missing": unprinted + contradicted,          # older names, kept
            "ok": not contradicted and bool(confirmed)}


def live_version(record: Record, aid: str) -> str:
    """The artifact that now stands for ``aid``: follow ``supersedes`` forward to the newest live version (the file
    as it is now). ``aid`` itself when nothing replaced it."""
    seen, cur = {aid}, aid
    for _ in range(50):
        n = record.get(cur)
        newer = [e["src"] for e in n.get("in", []) if e.get("rel") == "supersedes" and e["src"] not in seen]
        if not newer:
            return cur
        cur = newer[-1]
        seen.add(cur)
    return cur


def _claims_on(res: dict[str, Any]) -> list[str]:
    """Claims built on a result: derived from it, or supported by it."""
    out = [e["src"] for e in res.get("in", []) if e.get("rel") == "derived_from"]
    out += [e["dst"] for e in res.get("out", []) if e.get("rel") == "supports"]
    return list(dict.fromkeys(out))


def _nums_of(v: Any) -> list[float]:
    """The numbers a registered value carries: its value, or k and n of a count."""
    if isinstance(v, bool):
        return []
    if isinstance(v, (int, float)):
        return [float(v)]
    if isinstance(v, dict):
        return [float(v[k]) for k in ("value", "k", "n") if isinstance(v.get(k), (int, float))
                and not isinstance(v.get(k), bool)]
    return []


def _same_printed(x: float, dec: int, v: float) -> bool:
    return round(abs(v), dec) == x or (dec == 0 and abs(abs(v) - x) < 0.5)


def claim_rests_on(record: Record, claim_id: str, res: dict[str, Any], values: dict[str, Any]) -> set[str] | None:
    """The registered values of ``res`` that one claim rests on, or None when that can't be told.

    A claim that binds measurements to this result rests on those keys (the record's claim check already makes its
    numbers follow from them). A claim that binds none rests on the values its statement states — and only when every
    number in the statement is one of this result's values; a number it doesn't carry (a p-value, a difference) could
    depend on any of them, so the answer is None."""
    from hypgraph.checks import numbers
    c = record.get(claim_id)
    body = c.get("body") or {}
    ids = {res.get("id"), res.get("code")}
    meas = [m for m in body.get("measurements") or [] if isinstance(m, dict) and m.get("key")]
    bound = {str(m.get("key")) for m in meas if m.get("result") in ids}
    # values it binds from other results must still stand: one result reproduced says nothing about another
    for other in {str(m.get("result")) for m in meas if m.get("result") and m.get("result") not in ids}:
        try:
            st = (record.get(record.resolve(other, str(res.get("inv") or ""))).get("state") or {})
        except Exception:  # noqa: BLE001 — a result that can't be read can't be vouched for
            return None
        if st.get("stale") or st.get("lifecycle") != "active":
            return None
    if bound:
        return bound if bound <= set(values) else None
    printed = numbers(str(body.get("statement") or ""))
    if not printed:
        return None
    keys: set[str] = set()
    for x, dec, _pct, _p in printed:
        hit = {k for k, v in values.items() if any(_same_printed(x, dec, n) for n in _nums_of(v))}
        if not hit:
            return None
        keys |= hit
    return keys


def claims_to_support(record: Record, res: dict[str, Any], values: dict[str, Any],
                      chk: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """Per value: the claims on ``res`` whose own values all reproduced, though another value of the same result moved
    (claim id, the keys it rests on). A claim whose values can't be told, or include a moved, unprinted or missing
    one, isn't listed — it stays stale for a worker to redo."""
    ok = set(chk.get("confirmed") or [])
    out = []
    for c in _claims_on(res):
        keys = claim_rests_on(record, c, res, values)
        if keys and keys <= ok:
            out.append((c, sorted(keys)))
    return out


async def reproduce_result(record: Record, inv: str, result_id: str, reproducer: Reproducer, *,
                           support_claims: bool = False) -> dict[str, Any] | None:
    """Re-run the code behind one result and file the instrument's run + result. None when there is nothing to
    re-run (no source on the run). Never raises: a failure is filed as a failed lab run.

    The re-run happens on the files as they are now, so the lab run ``uses`` the live version of every artifact the
    author's run used. ``support_claims`` (re-verification of a stale result): when every registered value is
    reproduced on the current files, the lab result ``supports`` each claim built on the author's result — the
    claim is fresh again with no model call. When some value moved, each claim whose own values (claim_rests_on) all
    reproduced gets a lab result of just those values that supports it — a claim about A's count comes back though B's
    moved; the others stay stale for a worker to redo."""
    res = record.get(result_id)
    runs = [e["src"] for e in res.get("in", []) if e["rel"] == "produced"]
    if not runs:
        return None
    run = record.get(runs[0])
    source = str(((run.get("body") or {}).get("config") or {}).get("source") or "")
    if not source.strip():
        return None
    values = (res.get("body") or {}).get("values") or {}
    try:
        out = reproducer(source)
        if inspect.isawaitable(out):
            out = await out
        stdout = str(out)
        err = ""
    except Exception as e:  # noqa: BLE001 — the failure is the finding
        stdout, err = "", f"{type(e).__name__}: {str(e)[:300]}"
    if err:
        chk: dict[str, Any] = {"confirmed": [], "unprinted": [], "contradicted": [], "found": [], "missing": list(values),
                               "ok": False}
    else:
        chk = check_output(values, stdout)
    n = len([k for k in values if k in chk["confirmed"] or k in chk["unprinted"] or k in chk["contradicted"]])
    parts = [f"{len(chk['confirmed'])} of {n} registered values confirmed by the output"
             + (f" ({', '.join(chk['within'])} within the spread its author stated)" if chk.get("within") else "")]
    if chk["unprinted"]:
        parts.append(f"not printed by the code (not evidence against): {', '.join(chk['unprinted'])}")
    if chk["contradicted"]:
        parts.append(f"CONTRADICTED by the output: {', '.join(chk['contradicted'])}"
                     + ("" if all(_spread(values.get(k)) for k in chk["contradicted"]) else
                        " — if a value varies run to run (a timing, an unseeded sample), seed it or register it with "
                        "its spread ([lo, hi]) or rel_tol"))
    if err:
        parts.append(f"the code failed: {err}")
    verdict = "; ".join(parts)
    state = "succeeded" if not err else "failed"
    # the instrument's run uses what the author's run used (the diff, the instance, the data file): a workflow reads
    # `tests_pass_current` and freshness off the lab run's own `uses`, not the author's
    links: list[dict[str, Any]] = [{"rel": "replicates", "to": run["id"], "data": {"differs": "same_code"}}]
    used = list(dict.fromkeys((live_version(record, e["dst"]), tuple(sorted((e.get("data") or {}).items())))
                              for e in run.get("out", []) if e.get("rel") == "uses"))
    links += [{"rel": "uses", "to": a, "data": dict(d)} for a, d in used]
    lab = record.create(author=INSTRUMENT, type="run", inv=inv, fields={
        "kind": "lab", "name": f"re-execution of {run['code']}", "state": state,
        "note": f"re-ran {run['code']}'s registered code: {verdict}"[:2000],
        "config": {"reproduces": run["id"], "stdout_tail": stdout[-1500:], "confirmed": chk["confirmed"],
                   "unprinted": chk["unprinted"], "contradicted": chk["contradicted"]}},
        links=links)
    # the instrument confirms numbers; what they mean is the author's result's outcome. A confirmed "4 of 5 tests
    # pass" is a confirmed failure, so a negative result re-run stays negative — `tests_pass` reads the outcome.
    author_outcome = str((res.get("body") or {}).get("outcome") or "")
    if chk["contradicted"] or err:
        outcome = "negative"
    elif not chk["confirmed"]:
        outcome = "inconclusive"
    else:
        outcome = "negative" if author_outcome == "negative" else "positive"
    lab_res = record.create(author=INSTRUMENT, type="result", inv=inv, fields={
        "summary": f"Re-executed {run['code']}'s code: {verdict}.", "kind": "computed", "outcome": outcome,
        "values": {k: v for k, v in values.items() if k in chk["confirmed"]}},
        links=[{"rel": "produced", "from": lab["id"]}])
    supported: list[str] = []
    every = bool(chk["confirmed"]) and not chk["contradicted"] and not chk["unprinted"] and not err
    if support_claims and every:
        for c in _claims_on(res):
            try:
                record.link(author=INSTRUMENT, src=lab_res["id"], rel="supports", dst=c,
                            why=f"re-run of {run['code']}'s code on the current files reproduced every value it registered")
                supported.append(record.get(c)["code"])
            except Exception as e:  # noqa: BLE001 — a claim that can't take the link stays stale; a worker redoes it
                log.info("re-verified %s but could not support %s: %s", lab_res["code"], c, e)
    elif support_claims and not err and chk["confirmed"]:
        for c, keys in claims_to_support(record, res, values, chk):
            try:
                code = record.get(c)["code"]
                part = record.create(author=INSTRUMENT, type="result", inv=inv, fields={
                    "summary": f"Re-executed {run['code']}'s code: the values {code} rests on ({', '.join(keys)}) "
                               f"reproduced on the current files; moved: {', '.join(chk['contradicted']) or 'none'}.",
                    "kind": "computed", "outcome": author_outcome or "positive",
                    "values": {k: values[k] for k in keys}},
                    links=[{"rel": "produced", "from": lab["id"]}])
                record.link(author=INSTRUMENT, src=part["id"], rel="supports", dst=c,
                            why=f"re-run of {run['code']}'s code reproduced every value this claim rests on")
                supported.append(code)
            except Exception as e:  # noqa: BLE001 — as above: it stays stale
                log.info("re-verified %s but could not support %s by value: %s", lab_res["code"], c, e)
    return {"run": lab["code"], "result": lab_res["code"], "ok": chk["ok"], "confirmed": chk["confirmed"],
            "unprinted": chk["unprinted"], "contradicted": chk["contradicted"], "missing": chk["missing"], "error": err,
            "supported": supported}


__all__ = ["Reproducer", "check_output", "claim_rests_on", "claims_to_support", "live_version", "reproduce_result"]
