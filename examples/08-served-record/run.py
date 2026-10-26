"""
08 · One record server, many processes — token-bound writes.

The record is served by `hypgraph serve --writable` with two tokens: one for the swarm (bound to the harness and
its seats), one for a person. The swarm runs in this process over HTTP; the Atlas is open in your browser on the
same server while it runs; a write without a known token gets 401, a write as an author the token isn't bound to
gets 403. The example starts the server for you, runs, shows the refusals it provoked on purpose, and stops it.

    python run.py
    python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import budget, cli, main, models, pricing, show

from hypswarm import HttpRecord, Seat, Task, run

HERE = Path(__file__).resolve().parent
PORT = 8765


def serve(record: str, tokens: dict[str, str]) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "hypgraph", "--db", record, "serve", "--writable", "--no-browser", "--port", str(PORT)]
    for tok, authors in tokens.items():
        cmd += [f"--token={tok}={authors}"]               # one argument: a token can start with a dash
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    for _ in range(60):
        try:
            httpx.get(f"http://127.0.0.1:{PORT}/api/graph/investigations", timeout=1.0)
            return p
        except httpx.HTTPError:
            time.sleep(0.25)
    p.kill()
    raise SystemExit("the record server did not come up: " + (p.stderr.read()[-800:] if p.stderr else ""))


if __name__ == "__main__":
    args = cli("08 · a served record with tokens", HERE)
    if not Path(args.record).exists():                          # the server serves an existing record
        from hypgraph import Graph
        Graph(args.record).close()
    swarm_token, person_token = "swarm-" + secrets.token_hex(12), "nic-" + secrets.token_hex(12)
    srv = serve(args.record, {swarm_token: "harness,analyst,critic,lead", person_token: "nicolas"})
    base = f"http://127.0.0.1:{PORT}"
    print(f"\nrecord server: {base}   (the Atlas; open it while the run goes)\n")
    try:
        # the boundary, shown before the run: no token → 401; a token writing as someone it isn't bound to → 403
        body = {"author": "analyst", "type": "question", "fields": {"text": "probe"}}
        r1 = httpx.post(f"{base}/api/graph/write", json=body, timeout=5)
        r2 = httpx.post(f"{base}/api/graph/write", json=body, headers={"Authorization": f"Bearer {person_token}"}, timeout=5)
        print(f"write with no token      → {r1.status_code}\nwrite as analyst with the person's token → {r2.status_code}\n")
        # scientific@1: the frozen pre-workflow profile (the example is about the served record); 01 runs the workflow (scientific@2)
        task = Task(title="Served record", profile="scientific@1",
                    mission="Two models were scored on the same items. items.csv is not attached: the counts are given in the mission "
                            "— A right on 812 of 1000, B on 800 of 1000. Record them as results and answer.",
                    questions=[("Q1", "What is A's accuracy?")])
        answers = {"Q1": {"summary": "Took A's count from the mission.", "values": {"acc_a": {"k": 812, "n": 1000}},
                          "claim": "A is right on 812 of 1000 items.", "scope": "The counts stated in the mission.", "answer": 0.812}}
        seats = [Seat("analyst", "worker"), Seat("critic", "reviewer"), Seat("lead", "lead")]
        rec = HttpRecord(base, token=swarm_token)
        res = main(run(task, seats, models(args, answers), record=rec, budget=budget(args), pricing=pricing(args)))
        show(res, quiet=args.quiet, trace=args.trace)
        print(f"\nthe Atlas is still up at {base} for 20 s …")
        time.sleep(20 if not os.environ.get("CI") else 0)
    finally:
        srv.kill()
