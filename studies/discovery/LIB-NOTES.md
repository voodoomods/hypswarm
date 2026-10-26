# What the libraries should do better — running notes

Kept while building the discovery harness and reading the real runs of 2026-10-25. Each item: what happened, what it
cost, what to change. Items move to CHANGELOGs when fixed.

## HypGraph

*Items 1, 2, 4, 5 and 10 shipped in hypgraph 0.4.3 (2026-10-26); the rest are open.*

1. ~~**Significance knows only its own test.**~~ **Fixed in hypgraph 0.4.3** (a named p / p_value / p_<test> field, bound or on a supporting result, backs the word). `SIGNIFICANCE_WITHOUT_TEST` is satisfied only by the record's
   two-proportion z-test on bound counts. A model that ran an exact McNemar test (the right test for paired items)
   and bound `p_exact = 0.0001` was refused twice and had to drop the word. *Change:* accept a bound measurement
   named `p` / `p_value` with a stated test (`test:` field on the result or claim) below the threshold; keep the
   record's own test as the fallback and record which one backed the word.
2. ~~**"No live support" with measurements bound.**~~ **Fixed in 0.4.3** (a bound measurement's result supports the claim). A claim written with explicit `measurements` pointing at a result,
   but no `derived_from` / `supports` link, passes the checks and shows "no live support" in its standing. The
   writer did bind the evidence; the derive step doesn't count it. *Change:* count a measurement's result as a
   line of support, or add the `derived_from` edge when measurements bind (as auto-binding already does).
3. **Whole-second timestamps.** "Written after the order" compares `created_at` strings with second resolution; a
   write in the same second as the order doesn't count. Only scripted models are that fast, but the examples sleep
   1.05 s per order to dodge it. *Change:* microseconds in `created_at`, or a per-write sequence number compared
   instead of time.
4. ~~**Link-grammar refusals cost real models 5–10 calls a run.**~~ **Fixed in 0.4.3** (the refusal names the relations that join, both ways); `register_run(experiment=Q1)` is still HypSwarm's to handle. `executes can't join run → question`, `supports
   can't join claim → run`, `derived_from can't join claim → experiment`: all seen in one software run. The messages
   are correct but the model keeps guessing. *Change:* on a wrong relation, name the relation that *would* join
   those two types ("a claim rests on a result: derived_from claim → result"), and let `register_run(experiment=Q1)`
   with a question code answer the question instead of refusing.
5. ~~**Enum refusals on every run.**~~ **Fixed in 0.4.3** (`schema.SYNONYMS`); the docstring part is HypSwarm's. `outcome must be one of positive, negative, …` and `kind must be one of finding,
   exclusion, …` appeared in every real run (01, 02, 03, 05, 06). *Change:* accept synonyms (`success` → positive,
   `pass` → positive, `fact` → finding) and put the list in the tool docstrings HypSwarm exposes (done partly in
   `register_run`'s description; `graph_add` should carry both lists).
6. **Numbers in prose that are counts.** "returns 3 rows" is refused because a small integer binds only to k/n;
   the honest rewrite moves it to the scope. Reasonable, but the message could say that directly ("3 is a count:
   bind it as k of n, or state it in the scope").
7. **The report check and questions** — fixed in 0.4.2; the same idea applies to `## Q2 —` headings that *restate*
   a question without the question mark. Watch for it in the discovery runs.
9. **"cannot" is an absolute.** `ABSOLUTE` lists `cannot` / `impossible`, and `_EPISTEMIC` excuses only "cannot
   conclude / say / rule out …". The honest abstention "the comparison cannot be made on the full set" is refused as
   an absolute; so is "the test module cannot be collected". Found by the discovery self-test and stub run. *Change:* extend the epistemic list with be-passives ("cannot be
   made / computed / compared / run / collected / determined") and procedural verbs ("cannot run / compute / compare").
8. **`hypgraph --help` crashed on a `%`** — fixed in 0.4.1; argparse help strings need `%%`. A test that renders
   every subcommand's help would have caught it.

10. ~~**Small integers that are not counts.**~~ **Fixed in 0.4.3** (a small integer binds to a value field the sentence names). Seen live in the stub run: "produced 0 trades" (`oos_trades = 0` as a
    value) and "capacity is 7 for 8 customers" (`capacity_total = 7`) are `UNBOUND_NUMBER` because an integer ≤ 12
    binds only to a k/n count. The honest sentence has to move the number into the scope. *Change:* let a small
    integer bind to a value field whose *name* is in the sentence ("trades", "capacity"), not only to counts.
11. **`SCOPE_MISSING` at < 10 characters** refused a scope of "items.csv". Correct, and the message says what to do;
    the first thing a new user hits, so the tool docstrings should say "scope: a sentence".
12. **A settled board that is "stuck".** T4 can never settle Q3 (no source exists), so every run ends `stuck` with an
    accepted report that says Q3 is unanswered. That is the right outcome with the wrong name. *Change (HypSwarm):*
    a question whose only claim is an accepted "no answer available" (a claim of kind `inconclusive`) should count
    as settled-as-unanswerable, and the run should end `settled`.

13. **A correct answer refused to death (real run, T1-3).** The one seed where A *is* significantly better: the
    stats seat ran an exact McNemar test (p = 0.017), was refused 15 times with `SIGNIFICANCE_WITHOUT_TEST`, and the
    run ended at the budget with no report. Item 1 is not cosmetic: a named test with a bound p must satisfy the word.
14. **Measurement shape is the second-largest friction** (`MEASUREMENT_MALFORMED` ×19, `MEASUREMENT_UNKNOWN_FIELD` ×4
    over 25 runs). Models write `{"name": …, "value": …}` without `result`/`key`, or name a field the result doesn't
    have. *Change:* when `result` is omitted and exactly one of the author's results has the field, bind to it; when
    the key is unknown, list the result's fields in the refusal.
15. **Restating is the third** (`RESULT_RESTATES` ×19): models re-register the same numbers to "finalise". The refusal
    is right; the tool docstring should say "the record keeps your result; bind claims to it, don't re-register".
16. **"No feasible assignment exists" fought `ABSOLUTE_WITHOUT_COUNT` seven times (T5-4).** The model had enumerated
    all 6,561 assignments and found 0 feasible — that *is* the count. "exists" after "no" should bind to a 0-of-n
    measurement the way "never" does, and the refusal should say so.

## HypSwarm

1. **A refused report is a lost report.** The 06 lead's report was refused three times and the run ended with no
   report at all (correct questions, settled board, nothing to read). *Change:* after the last refusal, accept
   `report_facts` alone as the report, marked "facts only; the lead's interpretation was refused: <codes>". The
   facts come from the record and cannot be wrong.
2. **Agent-seat budgets are post-hoc.** A framework agent reports calls when it ends; the per-order cap can't stop
   it mid-way. `calls_left` is passed and the bridges cap their loops with it, but a bridge that ignores it can
   overspend one order. *Change:* a meter hook the bridge calls per model call (`order.meter.tick()`), so the
   reservation grows as the agent runs.
3. **A fetch refused by policy should say "stop".** In 04 the pod's firewall returned 403 for every URL form and
   the researcher tried ~40 of them. The tool returned the raw `ProxyError`. *Change:* the host's fetch tool should
   recognise a policy refusal (403 from a proxy, allowlist miss) and return "this host is not reachable from here;
   no URL form will change that; report it" — one call instead of forty. The discovery harness's fetch does this.
4. **CrewAI floor.** Custom `BaseLLM`s only get native tool calls from 1.15; a fresh resolve picked 1.6. Pinned.
   Generally: every bridge's extra should pin the first version whose integration path was tested, and
   `tests/test_bridges.py` should assert the version it was written against.
5. **PydanticAI reports tool args as text.** The seat log built `dict()` from it and crashed after the agent had
   finished. Fixed; the lesson is that bridges should normalise everything they read from a framework before the
   worker sees it (`AgentOutcome` could validate its own fields).
6. **The lead's turns are spent on refusals it can't fix.** The lead re-submitted the same heading three times.
   *Change:* on a report refusal, hand the lead the exact sentence and the rule, and on the second identical
   refusal rewrite the sentence mechanically (drop the flagged word) before giving up.
7. **Order text for a question target carries nothing about the data.** Workers call `list_files` + `read_file` on
   every order (06: two calls per order before any work). *Change:* the order text could name the files the task
   registered, with sizes, so a worker goes straight to python.
8. **Examples' stub sleeps.** `examples/_common.py` sleeps 1.05 s per order because of HypGraph item 3. Remove when
   that is fixed.
9. **`stopped` was empty after `stop()`** — fixed ("stopped"). A `RunResult.stopped` enum would have caught it.

10. **Budget hits are silent failures.** 6 of 25 R runs ended "budget: warning threshold"; 5 had no accepted report.
    The run should end with the facts report regardless (item 1 above) and the summary line should say which
    orders were open and what they were refused on, so a budget hit reads as a diagnosis, not a blank.
11. **Per-order calls for small work are high even when nothing is refused.** T4 (two lookups) took 28–43 calls
    under R and 2 under P: list_files, read_file, fetch, show, find, register, claim, return, review, report. The
    order should carry the files and the sources already in the record (item 7), and a question with a sourced
    claim should settle without a separate review when the profile says so.

## The discovery harness itself

- P is R's worker loop minus the record (`ploop.py`): the same prompt text, the same tools. If P wins somewhere,
  that is a real finding about the record's overhead, not about a weak baseline.
- T4 serves its own pages so the test is deterministic and costs no egress; the famous-date question deliberately
  has no page. The fetch tool answers an off-host URL with the index of what exists, so the model can't burn calls
  on URL variants (HypSwarm item 3).
- The checkers use HypGraph's own regexes (`language.asserted`, `_EDGE`, `_OPTIMAL`, `_PASSES`), so a P violation is
  by construction a sentence R would refuse. That is the fairness guarantee of the study.
