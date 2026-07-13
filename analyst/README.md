# 6 · ANALYST — Elif

**What can BGTS actually prove — and where are the holes?**

A question the sales team genuinely cannot answer today.

## Run it
```bash
python -m analyst.analyst --coverage
```

## Your levels
- **L1** — Load all 12 records into a DataFrame. Count by domain, region,
  technology, client type. Print a clean summary.
- **L2** — A coverage / gap map: which `domain × region` combinations have
  proof, and which are **empty**? Chart it. Flag engagements with no outcome.
- **L3** — A Streamlit dashboard. Cluster the engagements.

## Your test data
| File | Why |
|---|---|
| `records/corpus.json` | 12 records, deliberately uneven |
| `expected/analyst_expected.json` | the answer key — look **after** you've done your own analysis |

**You should find:** 15 `domain × region` combinations with no proof point at
all, and that `eng-12` is the only engagement with no measurable outcome.

**Success:** show your gap map to someone in sales. If they learn something
they didn't know, you've succeeded.
