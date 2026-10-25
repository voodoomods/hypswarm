# 05 · Optimization — "optimal" needs a bound

**Profile** `optimization` · **seats** modeller, solver (workers), verifier (reviewer), lead · **toolkits** files, python · **instrument** on

Six customers, three depots with capacity, a cost per assignment. Minimise total cost. 3^6 = 729 assignments, so
the instance is enumerated exactly and the bound is the objective.

```bash
python run.py --fresh
python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh
```

## What happens

```
[solver on T1] refused: result refused:
  - a result reports an objective value without saying whether the solution is feasible [OBJECTIVE_WITHOUT_FEASIBILITY]
[solver on T1] run RUN2 → result RS1 → claim CL1 — "The minimum total cost is 24, and the solution is optimal: …"
reproduced  result=RS1 confirmed=['bound', 'enumerated_feasible', 'feasible', 'gap', 'objective']
```

1. The scripted solver first registers a "greedy" result with an objective and nothing else. **Refused**: an
   objective without feasibility is not a result in this profile.
2. It then registers the enumeration: `objective`, `feasible = true`, `bound = objective`, `gap = 0.0`, and the
   number of feasible assignments it checked, with the code. The claim may say "optimal" because a bound meets the
   objective.
3. The instrument re-runs the enumeration and confirms all five values; the verifier reviews; Q1 settles.

## Rules this example shows

- `OBJECTIVE_WITHOUT_FEASIBILITY` — a result with `objective` and no `feasible` is refused.
- `OPTIMAL_WITHOUT_BOUND` — "optimal", "best possible", "cannot be improved" need a supporting result with `bound`
  or `gap`. Without one, say "best found".
- `feasible_bounded` — the order's done-when: objective, feasible = true, and a bound or gap.

## Making it yours

Replace the enumeration with OR-Tools / PuLP / scipy in the solver's code and register the solver's own gap; the
verifier checks feasibility against the constraints the order carries.
