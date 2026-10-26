# Change suite — results

_Predictions locked in PLAN-CHANGE.md, sha256 9f8b76d82293e43c…_

| family | cond | runs | fired | harmful: current | harmful: STALE shipped | unaffected right | harmless: current | $ | calls | R: questions redone | R: re-verified / supported |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | P | 5 | 5 | 4/4 | 0/4 | 5/5 | 1/1 | 0.013 | 28 | — | — |
| C1 | R | 5 | 5 | 2/4 | 0/4 | 3/5 | 1/1 | 0.153 | 371 | 10 (0:Q1,0:Q2,1:Q1,1:Q2,2:Q1,2:Q2,3:Q1,3:Q2,4:Q1,4:Q2) | 14 / 1 |
| C2 | P | 5 | 5 | 4/4 | 0/4 | 5/5 | 1/1 | 0.010 | 36 | — | — |
| C2 | R | 5 | 5 | 3/4 | 0/4 | 3/5 | 0/1 | 0.109 | 374 | 9 (0:Q1,0:Q2,1:Q1,1:Q2,2:Q1,2:Q2,3:Q1,3:Q2,4:Q1) | 14 / 5 |
| C3 | P | 5 | 2 | 1/1 | 0/1 | 0/— | 1/1 | 0.016 | 29 | — | — |
| C3 | R | 5 | 4 | 1/3 | 0/3 | 0/— | 0/1 | 0.199 | 356 | 4 (0:Q1,1:Q1,2:Q1,4:Q1) | 5 / 1 |
| C4 | P | 5 | 5 | 3/4 | 1/4 | 5/5 | 1/1 | 0.003 | 16 | — | — |
| C4 | R | 5 | 5 | 3/4 | 0/4 | 4/5 | 1/1 | 0.064 | 228 | 3 (0:Q1,2:Q1,3:Q1) | 0 / 0 |
| C5 | P | 5 | 3 | 2/2 | 0/2 | 0/— | 1/1 | 0.011 | 44 | — | — |
| C5 | R | 5 | 5 | 1/4 | 0/4 | 0/— | 0/1 | 0.135 | 337 | 3 (0:Q1,1:Q1,4:Q1) | 1 / 0 |

## Predictions (PLAN-CHANGE.md §4)

- **1 · P ships stale answers** (≥ 40 %; met when the 95 % lower bound > 15 %): NOT MET — 1/15 (7%, interval 1%–30%)
- **2 · R ships no stale answer** (0 %): MET — 0/19
- **3 · R is current more often** (R − P ≥ 20 points on harmful changes): NOT MET — R 10/19 (53%) vs P 14/15 (93%)
- **4 · R redoes only what moved** (after a harmful change, no question the change didn't touch is redone; after a harmless one, nothing is redone in ≥ 4 of 5 runs): NOT MET — 13/24 redone questions were affected ones; harmless runs with nothing redone 1/5
- **5 · cost** (we predict no cost win: R ≥ 5× P per run): MET — ratio 12.5; cost per current artifact P $0.0028 vs R $0.0550

Runs where the change never fired (the old answer was never computed by a tool; excluded above): C3-0-P, C3-1-P, C3-3-P, C3-3-R, C5-0-P, C5-2-P
