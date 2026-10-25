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
import re
from collections.abc import Awaitable, Callable
from typing import Any

from .record import INSTRUMENT, Record

Reproducer = Callable[[str], "str | Awaitable[str]"]

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


def check_output(values: dict[str, Any], stdout: str) -> dict[str, Any]:
    """What the re-run's output says about each registered value, kept apart because they mean different things:

    confirmed    the value appears in the output (at its own precision, or as a percentage)
    unprinted    the code computed it but printed nothing matching — not evidence against; the author should print
                 what they register (E′, 2026-10-25: 116 of 258 'not reproduced' were this, and a false negative
                 sent reviewers recomputing more than before)
    contradicted the output prints a *different* number next to this value's name

    ``ok`` is true when nothing is contradicted and at least one value is confirmed."""
    printed = _numbers(stdout)
    confirmed: list[str] = []
    unprinted: list[str] = []
    contradicted: list[str] = []
    for name, v in (values or {}).items():
        want: list[float] = []
        if isinstance(v, dict):
            if "k" in v and "n" in v:
                want = [float(v["k"]), float(v["n"])]
            elif isinstance(v.get("value"), (int, float)):
                want = [float(v["value"])]
        elif isinstance(v, (int, float)):
            want = [float(v)]
        if not want:
            continue
        if all(_matches(w, printed) for w in want):
            confirmed.append(name)
        elif any(not _matches(w, [x]) for w in want for x in _labelled(name, stdout)) and _labelled(name, stdout):
            contradicted.append(name)
        else:
            unprinted.append(name)
    return {"confirmed": confirmed, "unprinted": unprinted, "contradicted": contradicted,
            "found": confirmed, "missing": unprinted + contradicted,          # older names, kept
            "ok": not contradicted and bool(confirmed)}


async def reproduce_result(record: Record, inv: str, result_id: str, reproducer: Reproducer) -> dict[str, Any] | None:
    """Re-run the code behind one result and file the instrument's run + result. None when there is nothing to
    re-run (no source on the run). Never raises: a failure is filed as a failed lab run."""
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
    parts = [f"{len(chk['confirmed'])} of {n} registered values confirmed by the output"]
    if chk["unprinted"]:
        parts.append(f"not printed by the code (not evidence against): {', '.join(chk['unprinted'])}")
    if chk["contradicted"]:
        parts.append(f"CONTRADICTED by the output: {', '.join(chk['contradicted'])}")
    if err:
        parts.append(f"the code failed: {err}")
    verdict = "; ".join(parts)
    state = "succeeded" if not err else "failed"
    lab = record.create(author=INSTRUMENT, type="run", inv=inv, fields={
        "kind": "lab", "name": f"re-execution of {run['code']}", "state": state,
        "note": f"re-ran {run['code']}'s registered code: {verdict}"[:2000],
        "config": {"reproduces": run["id"], "stdout_tail": stdout[-1500:], "confirmed": chk["confirmed"],
                   "unprinted": chk["unprinted"], "contradicted": chk["contradicted"]}},
        links=[{"rel": "replicates", "to": run["id"], "data": {"differs": "same_code"}}])
    outcome = "negative" if chk["contradicted"] or err else ("positive" if chk["confirmed"] else "inconclusive")
    lab_res = record.create(author=INSTRUMENT, type="result", inv=inv, fields={
        "summary": f"Re-executed {run['code']}'s code: {verdict}.", "kind": "computed", "outcome": outcome,
        "values": {k: v for k, v in values.items() if k in chk["confirmed"]}},
        links=[{"rel": "produced", "from": lab["id"]}])
    return {"run": lab["code"], "result": lab_res["code"], "ok": chk["ok"], "confirmed": chk["confirmed"],
            "unprinted": chk["unprinted"], "contradicted": chk["contradicted"], "missing": chk["missing"], "error": err}


__all__ = ["Reproducer", "check_output", "reproduce_result"]
