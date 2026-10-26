# Change suite — real run, 2026-10-26 (internal)

*DeepSeek-V4.1-Flash through the pod proxy. 5 families × 5 seeds × {P, R} = 50 runs: a smoke run (C2 seed 0),
lane 1 (C1), then six parallel lanes (C2–C5). $0.713 total (P $0.053, R $0.660) against a $3 cap. Predictions locked
in `PLAN-CHANGE.md` (sha256 9f8b76d8…, printed in `results.md`). `results.md` is the generated table, `rows.json`
every artifact and score. Not for publication.*

## The headline

**The suite fails by its own rule (PLAN-CHANGE.md §4): P shipped a stale answer in 1 of 15 harmful runs, under the
15 % line.** Told once in the mission that files and pages may change, the prompted single agent re-hashed or
re-read before answering in nearly every run and reported the post-change numbers, often saying so ("the file
changed mid-task; I re-derived every number from the file as it now stands"). Its one stale answer (C4 seed 2)
came from a two-call run that fetched the page once and answered.

R never shipped a stale answer, and **every report R got accepted was current (10 of 10 on harmful changes)**. But R
lost the report in 9 of 19 harmful runs. Where the board settled a question in those runs, the record held the
right answer; the lead did not get a report through. That makes R current less often than P, at 12.5× the cost per
run. And the record's report check **does not read the answers block**: a report with the pre-change answers passes
it on every one of those records, so R's zero stale answers came from the lead copying fresh claims, not from the
check.

| | P | R |
|---|---|---|
| harmful runs where the change fired | 15 | 19 |
| current | 14 / 15 (93 %) | 10 / 19 (53 %) |
| stale answer shipped | 1 / 15 (7 %, Wilson 1–30 %) | 0 / 19 |
| accepted report, when there was one, current | — | 10 / 10 |
| calls per run | 2–12 | 29–80 |
| runs ending at the budget's warning line | 0 / 25 | 10 / 25 |
| $ per run | $0.002 | $0.026 |
| $ per current artifact | $0.0028 | $0.0550 |

## Every prediction

| # | prediction | result |
|---|---|---|
| 1 | P ships stale in ≥ 40 % of harmful runs (met when the Wilson lower bound > 15 %) | **NOT MET.** 1 / 15, 7 % (1–30 %). |
| 2 | R ships no stale answer | **MET.** 0 / 19. |
| 3 | R is current more often than P by ≥ 20 points | **NOT MET.** R 53 % vs P 93 %, so 40 points the other way. |
| 4 | R redoes only what moved: no untouched question redone after a harmful change, and nothing redone after a harmless one in ≥ 4 of 5 runs | **NOT MET.** 11 of 24 redone questions were untouched ones. 1 of 5 harmless runs had nothing redone. |
| 5 | No cost win: R ≥ 5× P per run | **MET.** 12.5×. P's cost per current artifact is also 20× lower than R's. |

**Fails if** P's stale rate is under 15 % (it is, at 7 %), or R ships any stale answer (it did not). By §5's table
this is the "1 fails" row: models re-check when told. The change suite moves to the long-horizon / many-agent
setting, where context is the constraint.

The interval matters. P's upper bound is 30 %, so 15 runs can't rule out a stale rate between 15 % and 30 %. The
point estimate and the agent's own words both say the prompt rule held here.

## Why R lost reports (9 of 19 harmful, 13 of 25 overall)

- **Where the board settled a question, the record had the answer.** In those runs a checked claim on the current
  file, tree, page or instance carries the post-change value. No checked claim in any lost-report record carries a
  pre-change value. Stale claims are marked STALE in the facts. Five runs settled only part of the board (C1 seed 1,
  C2 seed 1, C3 seeds 1, 2 and 4, C5 seed 4 left a question answered, open or in progress).
- **The check would have passed a plain report.** For all 13 lost-report records, the record's own facts, one
  line of interpretation and the post-change answers block pass `check_text` with no errors. The check did not
  refuse a correct report; the lead never submitted one that passed.
- **It would also have passed a stale one.** The same report with the *pre-change* answers block passes on all 13.
  HypGraph's report check skips fenced blocks (`report_check._SKIP_BLOCK`), and the answers block is fenced. So
  nothing in the record stops a lead from shipping a stale answer in the block; prediction 2 held because the
  leads copied from fresh claims.
- **What the lead did instead is not known.** The runner kept the report only when accepted, and the scheduler's
  `report_missing` event and the lead's report turns weren't saved in the row. Six of the 13 also stopped at
  the budget's warning line, where nothing more is issued but the report still gets its turns. **Fixed for the
  next run:** each R row now keeps `report_events` and `report_turns`.

So R's measured weakness here is the last step, not freshness: the record noticed every change it saw, and
everything it delivered was current, but the last step is also unguarded.

## Redo — the locked metric and a labelled diagnostic

The locked metric counts a question as redone when an order after the change re-asks a gate an earlier order on
that question already asked. That counts reworks the change didn't cause, such as a worker who came back without
a claim. The diagnostic below (not a prediction) labels each redone question by the order that re-asked it:
*change-driven* when its rework note or stage reason names stale or superseded evidence, *other* when it doesn't.

| after a harmful change | questions |
|---|---|
| redone, affected by the change | 13 |
| redone, untouched, change-driven | 6 |
| redone, untouched, other reason | 5 |

| after a harmless change | runs |
|---|---|
| nothing redone (locked metric) | 1 / 5 |
| nothing change-driven redone (diagnostic) | 3 / 5 |

Prediction 4 fails on either count. The six change-driven redos of untouched questions have two causes in the
record:

- **One result answered two questions.** In C1 the analyst registered `a_correct` and `b_correct` in one run.
  When B's labels moved, re-verification contradicted `b_correct`, and Q1's result fell with it, although
  `a_correct` reproduced. Re-verification restores a result only when every value reproduces.
- **One source answered two questions.** In C4 both answers come from the same page. The page edit made Q1's
  source stale too, though its passage about the opening year was unchanged.

The two harmless runs with a change-driven redo (C1 seed 4, C5 seed 4) are the same mechanism. The bytes changed,
so the file artifact was superseded. Re-verification ran 34 times in the suite and re-supported claims 8 times. It
did not bring every unchanged answer back.

## Disclosures

1. **First launch of lanes 2–6 never ran.** The launch line backgrounded `cd` and the environment with lane 1, so
   lanes 2–6 started in the wrong folder and exited without a model call. No spend. They were relaunched from a
   script that sets the folder and environment first.
2. **Checker fix 1, before lanes 2–6.** Both conditions in lane 1 wrote a flat answers block with no question keys,
   for example `{"a_correct": 821, "b_correct": 788, …}`, and the checker scored it as unanswered. The checker now
   reads a flat block as answering every question by field name. This applies to both conditions. Lane 1 and the
   smoke run were rescored from their stored artifacts. Lanes 2–6 were scored with the fix.
3. **Checker fix 2, found while scoring.** P wrote lowercase keys (`"q1"`) on C2 seed 4 and was marked wrong. Keys
   are now read in any case, for both conditions, and the merge rescored every row (`change_run.py --merge
   --rescore`). One row changed: C2 seed 4, P, harmless, from not current to current. No prediction moved.
4. **The smoke run is C2 seed 0.** It ran with the same settings and code as the lanes and is merged as those rows.
5. **Six runs where the change never fired are excluded** as the plan says: P on C3 seeds 0, 1, 3 and C5 seeds 0
   and 2, and R on C3 seed 3. In those runs no tool output ever matched the old answer's pattern, so nothing
   changed. Two of the P runs report the pre-change answer, which was still the true answer in their world.
6. **The checker scores what was shipped.** R's lost-report runs count as not current under prediction 3, as
   the plan says they should. The record-level observations above are a diagnostic, not a rescore.

## What this changes

- **The lead claim "the record notices when the world changes; a prompt doesn't" is not supported here** and is
  not used publicly. What held: R shipped no stale answer, and every report it delivered was current.
- **The report check now reads the answers block** (hypgraph 0.5.2, voodoomods/hypgraph PR #7: `REPORT_ANSWER_STALE`,
  `REPORT_ANSWER_UNBACKED`, `REPORT_ANSWERS_UNREADABLE`). On these records the plain report with the pre-change
  answers is refused on 19 of 20 instances; 11 of R's 12 accepted reports still pass, and all 20 accepted reports of
  the 2026-10-25 discovery run do. The refused one (C2 seed 0) is right to be refused: the record's only current
  claim on Q2 says "6 of the 6 tests passed" while the report says 5. That is also the one stale answer set it
  passes. **Corrected:** this said the claim's result had no `uses` link to the code tree. It has one: run RUN13
  names A8, the tree after the commit, and ran `python -m pytest -q tests`; the instrument re-ran that code and also
  got 6 passed. Running the same command in that run's folder now gives 5 passed, 1 failed, and replaying the change
  in a fresh copy gives 5 right after it (not Python's bytecode cache). What made the run see 6 isn't recoverable
  from what was kept (the workers' tool calls weren't logged). A HypGraph rule for results that name no file (stale
  once an input file changes after them) was built on a branch and measured: of 647 results in these records, 41
  name no file and none was written before a file changed, so it changes nothing here and is not pushed.
- **The R failure to fix is the report step.** The record was right in all 13 lost reports, and a plain report
  would have passed. The next run logs the report turns. A harness fallback is also worth testing: when the lead
  submits nothing that passes, assemble the answers from checked, fresh claims.
- **Re-verification needs to work per value.** It should restore a result's fresh values, or split a run's values
  by question, so one moved value doesn't sink an untouched question. Per-passage source freshness already exists
  (`contains_passage`). The C4 redo suggests the passage recorded for Q1 spanned both facts.
- **The setting to test next is where the prompt rule should break**: long runs, many agents, and a change landing
  after the agent's context has turned over. Here the whole task fit in one context, and the agent re-checked.
