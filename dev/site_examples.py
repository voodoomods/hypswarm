"""
hypswarm.com's live runs: run this repo's five scripted examples, then export each record as a verifiable bundle that
carries the run's telemetry, so the homepage can replay the swarm at work.

    python dev/site_examples.py          # writes site/data/examples/*.bundle.json

01 scientific · 02 software · 03 trading · 04 knowledge · 05 optimization. The models are HypSwarm's scripted ones
(free, deterministic answers computed by the example itself). A scripted reply is instant, so each model call is
paced: 0.35–1.4 s, from a seeded generator, so the replay shows calls in flight the way a real provider's would.
The pacing is stated on every example page; the record and its hash chain are exactly what the run wrote.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data" / "examples"
EXAMPLES = {"scientific": "01-eval-report", "software": "02-software-tests", "trading": "03-paper-trading",
            "knowledge": "04-sourced-brief", "optimization": "05-optimal-with-bound"}

# runs one example as __main__ with the scripted model's replies paced (the example itself is unchanged)
PACED = r"""
import asyncio, random, runpy, sys
from hypswarm.providers import stub
rng = random.Random(int(sys.argv[2]))
inner = stub.StubModel.complete
async def paced(self, *a, **k):
    await asyncio.sleep(rng.uniform(0.35, 1.4))
    return await inner(self, *a, **k)
stub.StubModel.complete = paced
script, sys.argv = sys.argv[1], [sys.argv[1]] + sys.argv[3:]
runpy.run_path(script, run_name="__main__")
"""


def main() -> None:
    hs = ROOT
    from hypgraph import Graph
    from hypgraph.bundle import verify_bundle

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for seed, (name, folder) in enumerate(EXAMPLES.items(), 1):
            rec = Path(tmp) / f"{name}.hypgraph"
            print(f"{name:13} running {folder} …", flush=True)
            subprocess.run([sys.executable, "-c", PACED, str(hs / "examples" / folder / "run.py"), str(seed),
                            "--fresh", "--quiet", "--record", str(rec)], check=True, cwd=hs / "examples" / folder)
            side = Path(str(rec) + ".telemetry.jsonl")
            if not side.is_file():
                sys.exit(f"{name}: the run wrote no telemetry (HypSwarm ≥ 0.1.0a7 writes it beside the record)")
            g = Graph(rec)
            try:
                inv = g.investigations()[0]["id"]
                b = g.export(inv, telemetry=side)
            finally:
                g.close()
            v = verify_bundle(b)
            assert v["ok"] and v["complete"], (name, v)
            text = json.dumps(b, ensure_ascii=False, separators=(",", ":"))
            (OUT / f"{name}.bundle.json").write_text(text, encoding="utf-8")
            tel = b["telemetry"]["events"]
            usd = sum(e.get("usd", 0) for e in tel if e["kind"] == "model_end")
            print(f"{'':13} {len(b['events'])} events, {len(b['nodes'])} nodes, {len(tel)} telemetry events, "
                  f"{sum(1 for e in tel if e['kind'] == 'model_end')} model calls (${usd:.4f}), {len(text):,} bytes")


if __name__ == "__main__":
    main()
