"""
04 · Knowledge — a brief where every claim cites what was actually read.

Three questions answered from sources. A claim without a source node is refused (CLAIM_WITHOUT_SOURCE): the record
holds what was read, not what was recalled. The scripted researcher writes a bare claim first, so you see the
refusal, then adds the source and the claim that cites it. With --model, a `fetch` tool over an allowlist is
registered so the model can read the pages for itself; whatever it reads goes into the record as a source node.

    python run.py
    python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import budget, cli, main, models, pricing, show

from hypswarm import Seat, Task, run, toolkits
from hypswarm.messages import Tool

HERE = Path(__file__).resolve().parent
ALLOW = ("en.wikipedia.org", "www.britannica.com")


def fetch(url: str) -> str:
    """GET a page (allowlisted hosts only) and return its visible text, at most 12,000 characters."""
    import re
    from urllib.parse import urlparse

    import httpx
    host = urlparse(url).hostname or ""
    if host not in ALLOW:
        return f"refused: {host} is not on the allowlist {ALLOW}"
    html = httpx.get(url, follow_redirects=True, timeout=20, headers={"User-Agent": "hypswarm-example/0.1"}).text
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)[:12000]


toolkits.register("fetch", lambda ctx: [Tool.from_function(fetch)], "GET over an allowlist, text only")

SOURCES = {   # the knowledge workflow's source: citation, url, the passage, retrieved, kind (secondary: encyclopaedias)
    "Q1": ({"citation": "Encyclopaedia Britannica, 'Peace of Westphalia'.", "url": "https://www.britannica.com/event/Peace-of-Westphalia",
            "passage": "…the treaties were signed on October 24, 1648…", "retrieved": "2026-10-25", "kind": "secondary"},
           "The Peace of Westphalia was signed on 24 October 1648.", "The treaties of Osnabrück and Münster.", "24 October 1648"),
    "Q2": ({"citation": "Wikipedia, 'Transistor'.", "url": "https://en.wikipedia.org/wiki/Transistor",
            "passage": "…the first working transistor was demonstrated at Bell Labs on December 23, 1947…", "retrieved": "2026-10-25", "kind": "secondary"},
           "The first working transistor was demonstrated at Bell Labs on 23 December 1947.", "The point-contact transistor of Bardeen and Brattain.", "23 December 1947"),
    "Q3": ({"citation": "Wikipedia, 'Mariana Trench'.", "url": "https://en.wikipedia.org/wiki/Mariana_Trench",
            "passage": "…the Challenger Deep … maximum known depth of 10,935 m …", "retrieved": "2026-10-25", "kind": "secondary"},
           "The deepest known point of the ocean, the Challenger Deep, is about 10,935 m deep.", "As surveyed in 2021 (GEBCO); earlier surveys differ by tens of metres.", "about 10,935 m"),
}

if __name__ == "__main__":
    args = cli("04 · knowledge: every claim cites a source", HERE)
    task = Task(title="Three facts, sourced", profile="knowledge",
                mission="Answer each question from a source you actually read. Add the source to the record (citation, url, the passage) "
                        "and write the claim that cites it. A claim with no source is refused.",
                questions=[("Q1", "When was the Peace of Westphalia signed?"), ("Q2", "When was the first working transistor demonstrated?"),
                           ("Q3", "How deep is the deepest known point of the ocean?")])
    answers = {q: {"first_try": ("graph_add", {"type": "claim", "fields": {"statement": claim, "scope": scope, "kind": "finding"},
                                              "links": [{"rel": "answers", "to": q}]}),
                   "source": src, "claim": claim, "scope": scope, "answer": ans}
               for q, (src, claim, scope, ans) in SOURCES.items()}
    seats = [Seat("researcher", "worker"), Seat("fact_checker", "reviewer"), Seat("lead", "lead")]
    res = main(run(task, seats, models(args, answers), record=args.record, budget=budget(args), pricing=pricing(args),
                   toolkits=["fetch"] if args.model else []))
    show(res, quiet=args.quiet, trace=args.trace)
