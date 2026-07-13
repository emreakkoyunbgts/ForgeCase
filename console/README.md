# 7 · CONSOLE — Serhat

**The web app that turns seven command-line tools into a product.**

Everyone else writes programs only an engineer could run. You build the thing
a salesperson can actually use. **At Demo Day, yours is the screen everyone
looks at** — because it is the only one that looks like a product.

## Run it
```bash
streamlit run console/console.py
```

## Your levels
- **L1** — Load the 12 records, show them in a table. Click one → see all its
  detail.
- **L2** — Search and filter (domain / region / technology). A **Generate**
  button that calls Taha's Generator and shows the case study. A visible badge
  when a client may **not** be named.
- **L3** — A **Download PDF** button that calls Ahmet's Publisher. An **Approve**
  step — download stays locked until a human approves.

## Your test data
| File | Why |
|---|---|
| `records/corpus.json` | the 12 records to browse and filter |
| `case_studies/eng-01_clean.json` | what your Generate button should display |
| `records/seed/eng-02.json` | the **only** record with `may_be_named: true` — show it differently |
| `records/corpus.json` (`eng-12`) | **no outcomes.** Show that gracefully — not a blank box, not an error |

## Success
Hand your laptop to someone non-technical. They browse to an engagement,
generate a case study, and download it — **with no instructions from you**.
