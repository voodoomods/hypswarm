"""The report the harness assembles when the lead's doesn't pass.

A run can end with the record holding every answer — a checked claim on the evidence as it is now for each question —
and still lose the report, because the lead never submitted one the record's check accepts. The record is the
answer; so when that happens the harness writes the report itself, from the record alone: the record's own facts, a
line saying the harness assembled it, and an answers block read off the current claims. No model is called.

Each question's answer comes from its current claim (live, not stale, not contested; a checked one first). The
fields a question asks for ("Answer as {"cost": <int>, "optimal": true|false}") are filled from that claim's bound
measurements — or, for a claim that binds none (one written by register_run), the values of the current results it
is derived from: one whose key (the result's own field) is the field, then one whose name is, then one the field is a
whole segment of ("cost" in "min_cost") when all such candidates agree. A field asked as true / false takes only a
boolean — or a 0 / 1 whose result key is that field: a gap of 0 that an author labelled "optimal" is not an answer of
"optimal: false". A field the claim doesn't bind is left out, never guessed; a question with no current claim is
answered null. The text must pass the record's check like any report, or it isn't used.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .record import Record

_FIELD = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*([^,}]*)')
_BOOL = re.compile(r"\btrue\b|\bfalse\b|<bool", re.IGNORECASE)


def asked_fields(question_text: str) -> list[tuple[str, str]]:
    """(field, kind) for each answer field a question names in its "Answer as {…}" format, in order; kind is "bool"
    when the format says true / false, else "value"."""
    out: dict[str, str] = {}
    for name, spec in _FIELD.findall(question_text or ""):
        out.setdefault(name, "bool" if _BOOL.search(spec) else "value")
    return list(out.items())


def _current(state: dict[str, Any]) -> bool:
    review = (state.get("review") or {}).get("state")
    return state.get("lifecycle") == "active" and not state.get("stale") and review != "contested"


def _measured(body: dict[str, Any]) -> list[tuple[str, str, Any]]:
    """(key, name, value) for each bound measurement; a count binds k, a bool-unit 0 / 1 is a bool."""
    out = []
    for m in body.get("measurements") or []:
        if not isinstance(m, dict):
            continue
        v = m.get("value") if m.get("value") is not None else m.get("k")
        if v is None or isinstance(v, (dict, list)):
            continue
        if str(m.get("unit") or "").lower() in ("bool", "boolean") and v in (0, 1):
            v = bool(v)
        out.append((str(m.get("key") or "").lower(), str(m.get("name") or "").lower(), v))
    return out


def _derived_values(record: Record, claim: dict[str, Any]) -> list[tuple[str, str, Any]]:
    """(key, "", value) for the values of the current results a claim is derived from or supported by."""
    out = []
    rids = [e["dst"] for e in claim.get("out") or [] if e.get("rel") == "derived_from"]
    rids += [e["src"] for e in claim.get("in") or [] if e.get("rel") == "supports"]
    for rid in dict.fromkeys(rids):
        node = record.get(rid)
        if node.get("type") != "result" or not _current(node.get("state") or {}):
            continue
        for k, v in ((node.get("body") or {}).get("values") or {}).items():
            unit = ""
            if isinstance(v, dict):
                unit = str(v.get("unit") or "").lower()
                v = v.get("value") if v.get("value") is not None else v.get("k")
            if v is None or isinstance(v, (dict, list, str)):
                continue
            if unit in ("bool", "boolean") and v in (0, 1):
                v = bool(v)
            out.append((str(k).lower(), "", v))
    return out


def _fill(field: str, kind: str, measured: list[tuple[str, str, Any]]) -> tuple[bool, Any]:
    f = field.lower()
    if kind == "bool":
        for key, name, v in measured:
            if isinstance(v, bool) and f in (key, name):
                return True, v
            if key == f and not isinstance(v, bool) and v in (0, 1):
                return True, bool(v)
        return False, None
    values = [(key, name, v) for key, name, v in measured if not isinstance(v, bool)]
    for pick in ([v for key, _n, v in values if key == f], [v for _k, name, v in values if name == f]):
        if pick:
            return True, pick[0]
    near = [v for key, name, v in values
            if any(n and (f in n.split("_") or n in f.split("_")) for n in (key, name))]
    distinct = list(dict.fromkeys(json.dumps(v) for v in near))
    if len(distinct) == 1:
        return True, near[0]
    return False, None


def assemble_answers(record: Record, inv: str) -> tuple[dict[str, Any], list[str]]:
    """The answers block the current claims give, and a note per question on where each answer came from."""
    answers: dict[str, Any] = {}
    notes: list[str] = []
    for row in record.question_board(inv):
        code = str(row["code"])
        claims = []
        for c in row.get("answers") or []:
            node = record.get(record.resolve(str(c), inv))
            if _current(node.get("state") or {}):
                claims.append(node)
        if not claims:
            answers[code] = None
            notes.append(f"{code}: no current claim answers it")
            continue
        checked = [n for n in claims if ((n["state"].get("review") or {}).get("state")) == "checked"]
        claim = (checked or claims)[-1]
        fields = asked_fields(str(row.get("text") or ""))
        measured = _measured(claim.get("body") or {}) or _derived_values(record, claim)
        got: dict[str, Any] = {}
        missing = []
        for f, kind in fields:
            ok, v = _fill(f, kind, measured)
            if ok:
                got[f] = v
            else:
                missing.append(f)
        if not fields:                               # no format named: the claim's own measurements
            got = {key or name: v for key, name, v in measured if key or name}
        answers[code] = got or None
        status = "checked" if claim in checked else "unchecked"
        notes.append(f"{code}: from {claim['code']} ({status})" + (f"; not bound by it: {', '.join(missing)}"
                                                                  if missing else ""))
    return answers, notes


def assembled_report(record: Record, inv: str) -> str:
    """The report the harness writes from the record when the lead's didn't pass: facts, a labelled note, and the
    answers block. Returns "" when the record has no current claim at all, or the text doesn't pass the check."""
    answers, notes = assemble_answers(record, inv)
    if not any(v is not None for v in answers.values()):
        return ""
    facts = record.report(inv)["markdown"]
    text = (facts + "\n\n## Interpretation\n\nThe lead's report did not pass the record's check, so the harness "
            "assembled this one from the record: each answer below is read off the current claim on its question, "
            "with no model call. Where a claim doesn't bind a field the question asks for, the field is left out.\n\n"
            + "\n".join(f"- {n}" for n in notes)
            + "\n\n```answers\n" + json.dumps(answers) + "\n```\n")
    check = record.check_text(text, inv)
    if any(f.get("level") == "error" for f in check.get("findings") or []):
        return ""
    return str(text)
