# The change suite — P3 of the profiles-as-workflows plan

*Status: plan, written 2026-10-26, nothing run on a model. The predictions below are fixed before any real run;
`results.md` prints the sha256 of this file. Spend cap: $3 on DeepSeek-V4.1-Flash through the pod proxy (expected
≈ $1.50). Nothing runs until the cap is approved.*

## 1. Why this test

The discovery study (PLAN.md) asked whether rules in the record beat the same rules in a prompt, on short tasks
where nothing changes. They didn't: the prompted agent wrote no violations in 25 of 25 runs, and the record cost
7–19× more. The plan for profiles-as-workflows (HypGraph `docs/profile-workflows-plan.md`) named the place where a
prompt *cannot* keep the rule, because the thing that moves is outside the agent's context:

> a commit after the tests (software), a retracted source (knowledge), a regime notice and an expired backtest
> (trading), a changed instance (optimization), a corrected file (scientific) … if R does not win **here**, the
> workflow design is wrong.

This suite is that test. It is also the first measure of the P3 instruments: the world watcher, re-verification on
the current files, the source re-fetch, and refresh orders (HypSwarm `world.py`, `reproduce.py`, `scheduler.py`;
hypgraph 0.5.2 freshness).

## 2. Design

**The change is silent and lands at the same point in both conditions.** Each instance has one change: a vendor's
corrected file (C1, C3), a teammate's commit (C2), an edited page (C4), a revised instance (C5). It is applied by the
tool both conditions share — the python or fetch call — right after the call whose output shows the *old answer*
(the old count, "6 passed", the old trade count, the old capacity, the old optimum). Neither condition is told.
Both missions carry the same sentence:

> The files and pages may change while you work — a vendor's corrected file, a teammate's commit, an edited page —
> and nobody will tell you. Before you give your final answer, make sure every number in it comes from the files
> and pages as they are at that moment.

| | **P — prompted** | **R — record** |
|---|---|---|
| model | DeepSeek-V4.1-Flash | the same |
| tools | python sandbox, files, fetch (C4) | the same, plus the record's tools |
| rules | the profile's rules and the sentence above in the prompt | the same text, and the `@2` workflow enforced; `run(..., watch=True)` |
| what notices the change | the agent, if it re-checks | the record: file hashes, the working tree as a head, page re-fetch |
| cap | 80 calls, $0.15 | the same |

**Families** (5 seeds each; seeds 0–3 change an answer, seed 4 is HARMLESS — the bytes change, the answers don't):

| family | profile | the change | affected | untouched |
|---|---|---|---|---|
| C1 | scientific | items.csv: the vendor fixes some of B's labels (seeds 0–2 flip significance) / rows reordered | Q2 B's count, significance | Q1 A's count |
| C2 | software | a commit to calc/fmt.py breaks 1–2 of 6 tests / adds a docstring line | Q2 passed, all pass | Q1 cents kept |
| C3 | trading | prices.csv: bad prints removed from the held-out window (seeds 0–2 flip the edge) / re-exported with 6 decimals | Q1 mean, trades, edge | — |
| C4 | knowledge | the page's capacity revised / an edit elsewhere on the page | Q2 capacity | Q1 opening year |
| C5 | optimization | a depot's capacity cut from 3 to 2 / a cost raised on a pairing nobody uses | Q1 cost | — |

The generators are seeded; `change_run.py --selftest` re-derives every truth (C2 by running pytest on both trees)
and checks the checker on honest and stale artifacts.

## 3. What is scored

Deterministic, over the final artifact's answers block (P's last message; R's accepted report). Nothing is scored
by a model.

- **current** — every affected answer is the post-change one.
- **stale shipped** — an affected answer is the pre-change one (where the two differ). This is the failure the suite
  exists to measure: a confident, sourced-looking answer about a world that no longer exists.
- **unaffected right** — the questions the change didn't touch are still right.
- **redone** (R) — questions the record asked for again after the change (an order re-asking a gate an earlier order
  on the same question already asked); a review or the workflow's next stage is not a redo.
- **cost** — $ and calls; cost per current artifact.

A run where the change never fired (no tool call ever computed the old answer) is reported and excluded.

## 4. Predictions

Counts are pooled over the 20 harmful runs per condition (seeds 0–3 × 5 families); rates come with Wilson
intervals.

1. **P ships stale answers in ≥ 40 % of harmful runs** (met when the interval's lower bound is above 15 %). The
   prompted agent computes the answer once, the world moves after it, and the rule to re-check before answering is
   an extra action after the agent believes it is done — the kind of instruction prompts don't keep.
2. **R ships no stale answer** (0 of 20). The watcher supersedes the changed file, the result goes stale, the
   review gate refuses to count a check on stale evidence, and the stage reopens until a fresh answer is checked.
3. **R is current more often than P by at least 20 points** on harmful runs. (R can fail other ways — the budget,
   a lost report; this prediction counts those against it.)
4. **R redoes only what moved**: after a harmful change no untouched question is redone, and after a harmless one
   nothing is redone in ≥ 4 of 5 runs — re-verification brings unchanged answers back with no model call.
5. **No cost win**: R costs ≥ 5× P per run. Cost per *current* artifact is reported for both; we do not predict
   that R wins it.

**Fails if** P's stale rate is under 15 % (a prompt rule is enough, and the watcher is a tax), or R ships any stale
answer (the design is wrong where it matters most). Either result is reported as it comes out; per the house rule,
negative results stay internal and the public material gets only what held.

## 5. What each outcome tells us

| if | then |
|---|---|
| 1 and 2 hold | "the record notices when the world changes; a prompt doesn't" is the lead claim for the workflows, measured |
| 1 holds, 2 fails | find the path a stale answer took through R and close it before anything is said publicly |
| 1 fails | models re-check when told; the change suite moves to the long-horizon / many-agent setting, where context is the constraint |
| 4 holds | re-verification is a cost story for change: unchanged answers come back at $0 |
| R's cost per current artifact < P's anywhere | say it there and only there |

## 6. Mechanics

- `python change_run.py --selftest` ($0), `--stub` ($0; `--stale-p` makes P write the pre-change answers to exercise
  the checker), `--model deepseek-ai/DeepSeek-V4.1-Flash --cap-usd 3` (the study). Lanes: `--families`, `--seeds`,
  `--seed-from`, `--out`, then `--merge`.
- 5 families × 5 seeds × 2 conditions = 50 runs; at the discovery study's prices (P ≈ $0.002, R ≈ $0.02 a run) and
  with R's extra rework, ≈ $1–1.50; cap $3.
- Results in `runs/<stamp>/results.md` with every prediction as met / not met, including the ones that fail.
