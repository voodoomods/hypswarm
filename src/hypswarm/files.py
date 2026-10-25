"""
Files a worker may trust: the record holds every data file as an artifact (sha256, path), and a worker reads a
file only when its bytes hash to a *live* artifact of the investigation. A file that matches a withdrawn artifact
(a notice declared it corrupt) is refused with the reason the record holds; a file the record never registered is
refused too. So a stale or planted file in the working folder cannot become evidence by being read.

    tools = file_tools(record, inv, Path("/work/team"))        # list_files, read_file
    run(task, seats, model, data_tools=tools, ...)
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .messages import Tool
from .record import Record


def _artifacts(record: Record, inv: str) -> dict[str, list[dict[str, Any]]]:
    """Registered artifacts by sha256: [{id, code, path, live, why}]."""
    out: dict[str, list[dict[str, Any]]] = {}
    for a in record.search("", "artifact", inv, 500):
        n = record.get(a["id"])
        st = n.get("state") or {}
        live = (st.get("lifecycle") or "active") == "active" and not st.get("fallen")
        why = (n.get("withdrawn") or {}).get("why") if isinstance(n.get("withdrawn"), dict) else ""
        out.setdefault(str(n["body"].get("sha256", "")).lower(), []).append(
            {"id": a["id"], "code": a.get("code", ""), "path": str(n["body"].get("path", "")), "live": live,
             "why": str(why or st.get("sentence", ""))[:200]})
    return out


def verify(record: Record, inv: str, data: bytes) -> dict[str, Any]:
    """What the record says about these bytes: {status: live | withdrawn | unknown, code, path, why}."""
    h = hashlib.sha256(data).hexdigest()
    hits = _artifacts(record, inv).get(h, [])
    if not hits:
        return {"status": "unknown", "sha256": h}
    live = [x for x in hits if x["live"]]
    x = (live or hits)[0]
    return {"status": "live" if live else "withdrawn", "sha256": h, "code": x["code"], "path": x["path"],
            "why": x["why"]}


def file_tools(record: Record, inv: str, folder: str | Path, *, max_bytes: int = 512_000) -> list[Tool]:
    """``list_files`` and ``read_file`` over ``folder``, each file checked against the record before it is trusted."""
    root = Path(folder).resolve()

    def _path(name: str) -> Path:
        p = (root / name).resolve()
        if not p.is_relative_to(root):
            raise ValueError(f"{name!r} is outside the working folder")
        return p

    def list_files() -> str:
        """The working folder's files and what the record says about each: live (registered, current), withdrawn
        (the record retired it — don't use it), or unknown (never registered — not evidence)."""
        rows = []
        for p in sorted(x for x in root.rglob("*") if x.is_file()):
            v = verify(record, inv, p.read_bytes()) if p.stat().st_size <= max_bytes else {"status": "too large"}
            rows.append(f"{p.relative_to(root).as_posix()}  {p.stat().st_size} bytes  {v['status']}"
                        + (f" ({v['code']})" if v.get("code") else "") + (f" — {v['why']}" if v["status"] == "withdrawn" else ""))
        return "\n".join(rows) or "(empty)"

    def read_file(name: str) -> str:
        """Read a file from the working folder — only if its bytes match a live artifact in the record. A withdrawn
        or unregistered file is refused with the reason."""
        try:
            p = _path(name)
        except ValueError as e:
            return f"refused: {e}"
        if not p.is_file():
            return f"error: no file {name!r}"
        if p.stat().st_size > max_bytes:
            return f"refused: {name} is {p.stat().st_size} bytes; the cap is {max_bytes}"
        data = p.read_bytes()
        v = verify(record, inv, data)
        if v["status"] == "withdrawn":
            return (f"refused: {name} matches {v['code']}, which the record withdrew — {v['why']}. Use the file the "
                    "record names as its replacement (list_files shows which are live).")
        if v["status"] == "unknown":
            return f"refused: {name} is not registered as an artifact in the record (sha256 {v['sha256'][:12]}…); it is not evidence"
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return f"({len(data)} bytes, not UTF-8 text; sha256 {v['sha256']}, artifact {v['code']})"

    return [Tool.from_function(list_files), Tool.from_function(read_file)]


__all__ = ["file_tools", "verify"]
