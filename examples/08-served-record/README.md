# 08 · One record server, many processes — token-bound writes

**Profile** `scientific` · **seats** analyst, critic, lead · **record** served by `hypgraph serve --writable`

The record is served with two tokens: one for the swarm (bound to `harness` and its seats), one for a person
(bound to `nicolas`). The swarm runs in this process over HTTP through `HttpRecord(url, token=…)`. The Atlas is
open on the same server while it runs.

```bash
python run.py --fresh
python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh
```

## What you see

```
record server: http://127.0.0.1:8765   (the Atlas; open it while the run goes)
write with no token      → 401
write as analyst with the person's token → 403
=== SETTLED in 2.7s — 6 calls ===
  Q1   settled      CL1 (checked by critic)
```

Two probes before the run show the boundary: a write without a token is 401; a write *as analyst* with the
person's token is 403 — a token writes only as the authors it is bound to, and the harness name is reserved (no
wildcard includes it). Reads stay open, so the Atlas and `my_work` work without a token.

## The command the example runs for you

```bash
hypgraph --db record.hypgraph serve --writable --no-browser --port 8765 \
  --token "$SWARM_TOKEN=harness,analyst,critic,lead" \
  --token "$NIC_TOKEN=nicolas"
```

and in the swarm: `run(task, seats, models, record=HttpRecord("http://127.0.0.1:8765", token=SWARM_TOKEN))`, or
`hypswarm run --record-url http://127.0.0.1:8765` with `HYPSWARM_TOKEN` set.

Keep the server on localhost or behind your own TLS / reverse proxy. A person's token goes to that person only;
their MCP server passes it with `--record-url … --token`.
