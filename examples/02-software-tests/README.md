# 02 · Software — the instrument runs the tests, not the tester

**Profile** `software` · **seats** implementer, tester (workers), reviewer, lead · **toolkits** files, python · **instrument** on

A CSV importer must keep a comma inside a quoted field (issue #412). `src/` holds the importer, three tests and a
fixture; they reach every worker's folder by hash.

```bash
python run.py --fresh
python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh
```

## What happens

```
[tester on T2] run RUN3 → result RS2
  claim refused: 'passes' is asserted, but no supporting result comes from an instrument-recorded run —
  tests must be run by the instrument, not reported [PASS_WITHOUT_INSTRUMENT_RUN]
  your order: T2: tests_pass NOT MET; claim_made NOT MET
reproduced  result=RS2 run=RUN5 confirmed=['exit_code', 'passed'] contradicted=[]
rework      order=T2 as T3: no live claim on Q2 since the order was issued
[tester on T3] graph_add(claim, derived_from RS2) → accepted
```

1. The tester registers the exact `pytest` command as the code of its run, with `passed = 3 of 3` and
   `exit_code = 0`, and writes the claim "passes all 3 of 3 tests" in the same call. **The claim is refused**: no
   instrument has run anything yet. The result stands; the order returns with `tests_pass NOT MET`.
2. The instrument re-executes the command in the sandbox and files a lab run that `replicates` RUN3; its result is
   positive and confirms both values. `tests_pass` is now met — by the instrument's run, not the tester's word.
3. The order is reworked ("no live claim"). Under a rework the record counts what the chain already produced, so
   `tests_pass` stays met; the tester writes the claim from RS2, which the record now accepts because a live lab
   run replicates the run behind it.
4. The reviewer's order carries the claim, the code and the re-run verdict; one `review(checked)` settles Q2.

## Rules this example shows

- `tests_pass` — "a result from an instrument-recorded run with a positive outcome": a report of passing never
  meets it.
- `PASS_WITHOUT_INSTRUMENT_RUN` — the word "passes" needs instrument backing: a lab result, or a live lab run that
  replicates the author's run with a positive result.
- `UNBOUND_NUMBER` with small integers: Q1's first claim said "returns 3 rows"; a 3 binds only to a count (k of n),
  so the honest version moves it to the scope ("fixtures/quoted.csv, 3 rows").

## Hooking it to your CI

Point the reproducer at your runner (a container, a clean checkout) and the record holds the same evidence your
pipeline does, by hash — see the engineers page.
