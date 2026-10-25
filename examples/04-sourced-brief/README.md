# 04 · Knowledge — a brief where every claim cites what was actually read

**Profile** `knowledge` · **seats** researcher (worker), fact_checker (reviewer), lead · **toolkits** `fetch` with `--model` (allowlisted GET)

Three questions, three sources, three claims.

```bash
python run.py --fresh
python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh     # the model reads the pages through `fetch`
```

## What happens

```
[researcher on T1] refused: claim refused:
  - link the evidence: at least one result, claim or source that supports it [EVIDENCE_MISSING]
  - numbers in the statement that no bound measurement … account for: 24, 1648 [UNBOUND_NUMBER]
[researcher on T1] graph_add(source) → added S1
[researcher on T1] graph_add(claim, cites S1) → added CL1
```

1. The scripted researcher writes the bare claim first ("signed on 24 October 1648"). **Refused**: no evidence, and
   the numbers come from nowhere.
2. It adds the source (citation, URL, the passage that says it, retrieval date), then the claim that `cites` it.
   Accepted: a cited source is evidence, and the numbers in its passage account for the numbers in the claim.
3. The fact-checker reviews; the lead's report is linted so no sentence treats an unreviewed claim as settled.

## Rules this example shows

- `CLAIM_WITHOUT_SOURCE` — the knowledge profile's validator: a finding must cite a source node. The record holds
  what was read, not what was recalled.
- `sourced` — the order's done-when: a claim on the target that cites a live source.
- A cited source's passage, citation and title account for the numbers in the claim (hypgraph 0.4.1).

## With a real model

`fetch(url)` is registered only with `--model`, over an allowlist (`en.wikipedia.org`, `www.britannica.com`). The
model reads a page, adds it as a source with the passage, and cites it. Change the allowlist to the sources you
trust; a host that registers no fetch tool gets a researcher that can only cite what is already in the record.
