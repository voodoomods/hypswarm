# 01 · Scientific — an eval report that holds up

**Profile** `scientific` · **seats** analyst, stats (workers), critic (reviewer), lead · **toolkits** files, python · **instrument** on

Two models were scored on the same 1,000 items. Does A beat B?

```bash
python run.py                                                   # scripted models, free
python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh   # a real provider, a few cents
```

## What happens

1. The scheduler reads the question board and issues two orders at once: Q1 to `analyst`, Q2 to `stats`
   (seats are matched on the words they `take`).
2. Each worker runs python on `items.csv`, then calls `register_run` once: the run, the result with its values,
   and the claim that answers the question, in one write. The claim's numbers are bound to the result's values.
3. The instrument re-runs each worker's code in the sandbox before any review and files a lab run that
   `replicates` the worker's: every printed value confirmed, or contradicted.
4. The critic gets a review order that carries the claim, its measurements, the code and the re-run verdict; one
   `review(checked)` settles the question.
5. The lead starts from `report_facts` and submits; the report is linted against the record.

## The rule this example shows

Q2 asks whether A is *significantly* better. The record runs a two-proportion z-test on the bound counts before it
lets that word through: with the generated data the honest sentence is the one you see in the report. Write it the
other way with a real model and you get

```
refused: 'significantly': the bound counts (812/1,000 against 800/1,000) differ by 1.2 points, 95% interval −2.2 to 4.6,
p = 0.49 (two-proportion z-test) — not significant at 0.05; say the difference and that it isn't significant
[SIGNIFICANCE_NOT_SHOWN]
```

## Afterwards

```bash
hypgraph --db record.hypgraph serve       # the Atlas: claims, standing, provenance, the refusal log
hypgraph --db record.hypgraph orders      # every order, its predicates, who held it
hypgraph --db record.hypgraph check report.md
```
