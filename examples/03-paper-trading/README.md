# 03 · Trading — a paper desk where "edge" needs out-of-sample returns after costs

**Profile** `trading` · **seats** quant (worker), risk (reviewer), lead · **toolkits** files, python · **instrument** on

`prices.csv` holds 1,000 daily closes. Thesis: after a five-day drop of 3 % or more, the next five days
mean-revert. Days 0–599 are the fitting window; days 600–999 are held out.

```bash
python run.py --fresh
python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh
```

## What happens

```
[quant on T1] refused: result refused:
  - a backtest result reports returns without the costs it charged [BACKTEST_WITHOUT_COSTS]
[quant on T1] run RUN2 → result RS1 → claim CL1 — … oos_return, insample_return, max_dd, trades, fees, slippage
reproduced  result=RS1 confirmed=['fees', 'insample_return', 'max_dd', 'oos_return', 'slippage', 'trades']
```

1. The scripted quant first registers a result with `oos_return` and nothing about costs. **The result is refused
   before it is a result** — in the trading profile a backtest without the costs it charged is not evidence.
2. It then registers the honest backtest: out-of-sample return, in-sample return, drawdown, trade count, fees and
   slippage, with the code. The claim says what the held-out window returned after costs; "edge" is asserted only
   if that number is positive.
3. The instrument re-runs the backtest and confirms all six values; the risk seat reviews; Q1 settles.

## Rules this example shows

- `BACKTEST_WITHOUT_COSTS` — a result with returns and no `fees` / `slippage` / `cost` field is refused.
- `EDGE_WITHOUT_OOS_COSTS` — "edge", "alpha", "outperforms", "profitable" need a supporting result that carries both
  an out-of-sample measure and the costs charged. In-sample, pre-cost returns are not an edge.
- `backtested_oos` is the order's done-when: a result with both an out-of-sample measure and a cost measure.
- **No live orders.** Nothing in hypswarm places one; the profile's notes say so to every seat; the completion
  criterion `position_recorded` asks for a *decision* node (size, stop, review date) `based_on` the claim.

## Making it yours

Register a read-only market-data toolkit (a function that fetches bars) and let the quant pull real history; the
record's rules don't change.
