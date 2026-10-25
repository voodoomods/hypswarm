# 07 · A person as the reviewer — over MCP

**Profile** `scientific` · **seats** analyst (worker), *you* (reviewer, external), lead · **toolkits** files, python · **instrument** on

The analyst answers; you review. Your seat is `external = True`: the scheduler issues it an order like any other
and waits for the record to say the order has left `open`. The record can't tell a person from an agent except by
name.

```bash
python run.py --auto --fresh      # a scripted analyst; a second process plays you (Graph(path) as 'nicolas')
python run.py --fresh             # a scripted analyst; the run waits up to 30 min for YOUR review
```

In the second form, from another terminal (Claude Code, Cursor, or the plain MCP server):

```bash
hypgraph --db record.hypgraph --as nicolas mcp
# then: my_work → review(<claim>, "checked", how, notes) → return_work
```

## What you see

```
[nicolas] reviewed CL1 and returned T2
=== SETTLED in 2.5s — 4 calls ===
  Q1   settled      CL1 (checked by nicolas)
```

The review order you receive carries the claim, its measurements, the result it rests on, the analyst's code and
the instrument's re-run verdict — so you judge; you don't recompute. Your verdict and your return are written as
`nicolas`; nobody else can write as you (bind a token to your name on a served record, example 08).

## If you don't show up

The order's lease runs out (`lease_minutes`, default 240; here `external_timeout_s`), the record returns it on your
behalf with a note saying so, and the scheduler decides: rework, another reviewer, or the lead. Example 09 shows
the other half — a run stopped with your order still open, resumed later with someone else in the seat.
