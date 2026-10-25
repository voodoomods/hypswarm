# 09 · Stop it, resume it; withdraw a file mid-run

**Profile** `scientific` · **seats** north, south (workers), critic, lead · **toolkits** files, python · **instrument** on

Two sites, two files, two questions.

```bash
python run.py          # always starts fresh: it needs both phases
```

## Phase 1 — a run stopped with an order open

The south seat is a person who never shows up (`external = True`). North answers; the host calls `stop()` at the
first return; the south order is still **open** in the record:

```
stopped: 'stopped'; orders in the record: T1=returned (north), T2=open (south)
```

## Phase 2 — resume, and a notice

The same investigation is resumed (`run(..., resume=inv)`) with a model in the south seat. The open order is
**adopted as it stands** — nothing is re-asked, north's work still counts, a new run node says it resumed:

```
adopt       seat=south order=T2 reworks=0
```

At the first return the host declares the south file corrupt and registers the fix:

```python
sched.notify("site_south.csv was exported in µg/L but labelled mg/L; use site_south_fixed.csv (mg/L).",
             stale=["site_south.csv"], add_files={"site_south_fixed.csv": SOUTH_FIXED})
```

What the record does with that, all mechanical:

```
notice      stale=['site_south.csv'] added=['site_south_fixed.csv']
artifact site_south.csv: withdrawn artifact
the last order issued (T5) carries it:
  NOTICES (read before anything else)
  - site_south.csv was exported in µg/L but labelled mg/L; use site_south_fixed.csv (mg/L).
read_file('site_south.csv') → refused: … withdrawn …
read_file('site_south_fixed.csv') → day,mg_l …
```

- the artifact is withdrawn with the notice as the reason;
- every order issued from then on carries the notice, and so does the lead's prompt;
- a worker's `read_file` refuses the stale bytes and reads the fixed file;
- anything that rested on the file — a result that `uses` it, a claim derived from that result, an order working
  on that claim — falls, and the open orders among them are cancelled as moot. Here nothing had been written from
  the bad file yet, so nothing fell; run it with `--trace` and move the notice later to watch a claim go AT RISK.

## Why this is the record's job

A run that dies leaves its state in the record, not in a process. A fact that changes — a corrupt file, a retracted
source — is declared once, in the record, and reaches every seat through the orders it issues. No agent has to be
told twice, and none can keep working on bytes the record no longer vouches for.
