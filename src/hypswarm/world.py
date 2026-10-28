"""
The world watcher: the record holds what the task's files and sources were when they were used; this keeps it in
step with what they are now — mechanically, with no model call.

Nobody has to tell the team that a teammate pushed a commit, that the data vendor corrected a file or that a page
was edited. Each scheduler round, ``World.sync()``:

    files    re-hashes every live artifact whose file is in the working folder; a file whose bytes changed gets a
             new artifact (same path, kind and meta) that ``supersedes`` the old one and keeps its ``part_of`` links.
             Every result whose run ``uses`` the old version goes STALE (hypgraph derives it); under a workflow
             profile, what rests on it goes AT RISK and its question's gate reopens.
    tree     for the software workflow: the working tree of the task's files as one ``kind=diff`` artifact
             (base → head sha, the files that changed), ``part_of`` every question. A commit is a new head that
             supersedes the old one, so tests on the old head stop counting — CI's rule, kept by the record.
    sources  with a host ``refetch(url) -> text``: every live source's page is fetched again and filed as an
             ``excerpt`` artifact ``derived_from`` the source, with ``contains_passage``. A page that no longer says
             what the source quotes makes the source STALE (an edit elsewhere on the page doesn't).

``sync()`` returns one plain sentence per change; the scheduler adds them to every order issued afterwards and to
the lead's prompts. What to do about the change is then the record's business: the instrument re-runs stale results
on the current files (``reproduce.reverify``), and the stage machinery reissues only the questions whose evidence
really moved.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hypgraph import GraphError

from .record import HARNESS, Record

Refetch = Callable[[str], str]
_SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git", ".mypy_cache", ".ruff_cache", ".venv", "node_modules"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _norm(text: str) -> str:
    t = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"<[^>]+>", " ", t)                       # a page fetched as HTML is read as its text
    return re.sub(r"\s+", " ", t).strip().lower()


def passage_in(passage: str, text: str) -> bool:
    """Whether a quoted passage still appears in a page's text: case and whitespace ignored, and a passage written
    with ellipses ("…signed on October 24, 1648…") needs each of its pieces, in order."""
    page = _norm(text)
    pieces = [p.strip(" .,;:'\"") for p in re.split(r"…|\.\.\.", _norm(passage))]
    pieces = [p for p in pieces if len(p) >= 3]
    if not pieces:
        return False
    at = 0
    for p in pieces:
        i = page.find(p, at)
        if i < 0:
            return False
        at = i + len(p)
    return True


BASELINE_DIR = "_base"


def seed_baseline(record: Record, inv: str, folder: str | Path | None, files: dict[str, bytes]) -> list[str]:
    """Keep the files as they were at the start. Their bytes are written under ``_base/`` in ``folder`` and the
    task's file artifacts (one per content: the record is content-addressed) are marked ``meta.baseline`` with that
    path. The watcher then never supersedes them: when a seat edits a working file, the new bytes become a new
    artifact *derived from* the original, and the original stays live — a question about the original ("which
    tests fail on the original semver.py?") is answered from ``_base/`` after the edit. Returns the codes marked."""
    codes = []
    for name, data in files.items():
        if folder:
            p = Path(folder) / BASELINE_DIR / name
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        mine = [a for a in record.search("", "artifact", inv, 500)
                if str(record.get(a["id"])["body"].get("sha256") or "").lower() == sha]
        if not mine:
            continue
        nid = mine[0]["id"]
        meta = dict(record.get(nid)["body"].get("meta") or {})
        meta["baseline"] = f"{BASELINE_DIR}/{name}"
        try:
            # an artifact is never revised; registering the same bytes again types an untyped one (kind) and
            # takes its meta with it — the task's file artifacts are untyped, so this is how they are marked
            out = record.create(author=HARNESS, type="artifact", inv=inv, fields={"sha256": sha, "path": name,
                                                                                     "kind": "file", "meta": meta})
            if (out.get("body") or {}).get("meta", {}).get("baseline"):
                codes.append(str(out.get("code") or nid))
        except GraphError:
            continue
    return codes


class World:
    def __init__(self, record: Record, inv: str, folder: str | Path | None = None, *, tree: bool = False,
                 refetch: Refetch | None = None, author: str = HARNESS):
        self.r, self.inv, self.author = record, inv, author
        self.folder = Path(folder) if folder else None
        self.tree, self.refetch = tree, refetch
        self.changes: list[dict[str, Any]] = []        # every change seen, for the run's events

    # ── helpers over the record ──────────────────────────────
    def _nodes(self, ntype: str) -> list[dict[str, Any]]:
        out = []
        for row in self.r.search("", ntype, self.inv, 500):
            st = row.get("state") or {}
            if (st.get("lifecycle") or "active") == "active" and not st.get("fallen"):
                out.append(self.r.get(row["id"]))
        return out

    @staticmethod
    def _part_of(n: dict[str, Any]) -> list[str]:
        return [e["dst"] for e in n.get("out", []) if e.get("rel") == "part_of"]

    def _questions(self) -> list[str]:
        return [q["id"] for q in self._nodes("question")]

    def _create(self, fields: dict[str, Any], links: list[dict[str, Any]]) -> dict[str, Any] | None:
        try:
            out: dict[str, Any] = self.r.create(author=self.author, type="artifact", inv=self.inv, fields=fields,
                                                links=links)
            return out
        except GraphError as e:
            self.changes.append({"kind": "error", "path": fields.get("path"), "why": str(e)[:200]})
            return None

    # ── the three watches ────────────────────────────────────
    def _files(self) -> list[str]:
        if not self.folder:
            return []
        notes = []
        arts = self._nodes("artifact")
        for n in arts:
            b = n.get("body") or {}
            path, kind = str(b.get("path") or ""), str(b.get("kind") or "")
            if not path or path == "." or kind == "excerpt" or "://" in path:
                continue
            f = (self.folder / path)
            try:
                if not f.resolve().is_relative_to(self.folder.resolve()) or not f.is_file():
                    continue
                data = f.read_bytes()
            except OSError:
                continue
            new = _sha(data)
            if new == str(b.get("sha256") or "").lower():
                continue
            base = str((b.get("meta") or {}).get("baseline") or "")
            if base:
                # the original, kept under _base/: it stays live; the working file's new bytes get their own
                # artifact, derived from it, the first time they diverge (later edits supersede that one)
                if any(x["id"] != n["id"] and (x.get("body") or {}).get("path") == path for x in arts):
                    continue
                fields = {"sha256": new, "path": path, "size": len(data)}
                for k in ("format", "kind"):
                    if b.get(k):
                        fields[k] = b[k]
                links = [{"rel": "derived_from", "to": n["id"]}] + [{"rel": "part_of", "to": q} for q in self._part_of(n)]
                out = self._create(fields, links)
                if out:
                    self.changes.append({"kind": "file", "path": path, "old": n["code"], "new": out["code"]})
                    notes.append(f"{path} changed on disk ({out['code']}, derived from {n['code']}); the original "
                                 f"stays at {base} ({n['code']}) — a question about the original is answered there")
                continue
            fields: dict[str, Any] = {"sha256": new, "path": path, "size": len(data)}
            for k in ("format", "kind"):
                if b.get(k):
                    fields[k] = b[k]
            if b.get("meta"):
                meta = dict(b["meta"])
                if "head_sha" in meta:
                    meta["base_sha"], meta["head_sha"] = meta["head_sha"], new[:12]
                fields["meta"] = meta
            links = [{"rel": "supersedes", "to": n["id"]}] + [{"rel": "part_of", "to": q} for q in self._part_of(n)]
            out = self._create(fields, links)
            if out:
                self.changes.append({"kind": "file", "path": path, "old": n["code"], "new": out["code"]})
                notes.append(f"{path} changed on disk ({n['code']} → {out['code']}): results computed from the old "
                             f"bytes are stale — recompute from the file as it is now")
        return notes

    def _tracked(self) -> dict[str, str]:
        """The task's files (the paths the record holds as plain file artifacts) and their current hashes."""
        if not self.folder:
            return {}
        paths = set()
        for n in self._nodes("artifact"):
            b = n.get("body") or {}
            p = str(b.get("path") or "")
            if p and p != "." and "://" not in p and str(b.get("kind") or "") != "excerpt":
                paths.add(p)
        out = {}
        for p in sorted(paths):
            f = self.folder / p
            if f.is_file() and not (set(Path(p).parts) & _SKIP_DIRS):
                out[p] = _sha(f.read_bytes())
        return out

    def _tree(self) -> list[str]:
        files = self._tracked()
        if not files:
            return []
        head = _sha("\n".join(f"{p} {h}" for p, h in files.items()).encode())
        cur = [n for n in self._nodes("artifact") if (n.get("body") or {}).get("path") == "."
               and (n.get("body") or {}).get("kind") == "diff"]
        if cur and str(cur[-1]["body"].get("sha256")) == head:
            return []
        keep = files if len(files) <= 40 else {}              # meta is bounded; past 40 files the change list is coarse
        if not cur:
            fields = {"sha256": head, "path": ".", "kind": "diff", "format": "tree",
                      "meta": {"base_sha": "task", "head_sha": head[:12], "files": sorted(files)[:200],
                               "hashes": keep}}
            self._create(fields, [{"rel": "part_of", "to": q} for q in self._questions()])
            return []
        old = cur[-1]
        before = dict((old["body"].get("meta") or {}).get("hashes") or {})
        changed = sorted(p for p in set(before) | set(files) if before.get(p) != files.get(p))
        fields = {"sha256": head, "path": ".", "kind": "diff", "format": "tree",
                  "meta": {"base_sha": str(old["body"]["sha256"])[:12], "head_sha": head[:12],
                           "files": changed[:200] or sorted(files)[:200], "hashes": keep}}
        links = [{"rel": "supersedes", "to": old["id"]}] + [{"rel": "part_of", "to": q} for q in self._part_of(old)]
        out = self._create(fields, links)
        if not out:
            return []
        self.changes.append({"kind": "tree", "old": old["code"], "new": out["code"], "files": changed})
        note = (f"the working tree has a new head {head[:12]} ({out['code']} supersedes {old['code']}; changed: "
                f"{', '.join(changed[:6]) or 'files'}): tests run on the old head no longer count — run them on this one")
        return [note]

    def _sources(self) -> list[str]:
        if not self.refetch:
            return []
        notes = []
        for src in self._nodes("source"):
            b = src.get("body") or {}
            url, passage = str(b.get("url") or ""), str(b.get("passage") or "")
            if not url or not passage:
                continue
            try:
                text = str(self.refetch(url) or "")
            except Exception:  # noqa: BLE001 — a page that can't be fetched no longer says anything
                text = ""
            has = passage_in(passage, text)
            sha = _sha(f"{src['id']}\n{text}".encode())
            ex = [self.r.get(e["src"]) for e in src.get("in", []) if e.get("rel") == "derived_from"]
            ex = [x for x in ex if (x.get("body") or {}).get("kind") == "excerpt"]
            live = [x for x in ex if ((x.get("state") or {}).get("lifecycle") or "active") == "active"]
            if live and str(live[-1]["body"].get("sha256")) == sha:
                continue
            fields = {"sha256": sha, "path": url[:500], "kind": "excerpt", "size": len(text),
                      "meta": {"source": src["id"], "contains_passage": has,
                               "fetched": time.strftime("%Y-%m-%dT%H:%M:%S")}}
            links = [{"rel": "derived_from", "to": src["id"]}] + ([{"rel": "supersedes", "to": live[-1]["id"]}] if live else [])
            out = self._create(fields, links)
            if out:
                self.changes.append({"kind": "source", "source": src["code"], "excerpt": out["code"], "contains": has})
                if not has:
                    notes.append(f"{src['code']}'s page ({url}) no longer contains its passage \"{passage[:80]}\" — "
                                 "claims citing it are stale; read the page as it is now")
        return notes

    def sync(self) -> list[str]:
        """One pass over files, the tree and sources; the sentences say what changed."""
        notes = self._files()
        if self.tree:
            notes += self._tree()
        notes += self._sources()
        return notes


__all__ = ["Refetch", "World", "passage_in"]
