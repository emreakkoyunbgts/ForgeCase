# 5 · LIBRARIAN — Arda

**Paste an RFP → get the past engagements that best prove we can do it.**

The problem a bid manager has at 11pm before a deadline.

## Run it
```bash
python -m librarian.librarian caseforge-testdata/rfp/rfp_01_realtime_payments.txt
```

## Your levels
- **L1** — Embed the 12 records. A plain question returns the 3 best matches.
- **L2** — An RFP paragraph returns ranked matches **with a reason** for each
  ("matched on: GCC, Kafka, core banking").
- **L3** — A grounded capability statement across the top matches. Same
  no-invention rule as the Generator.

## Your test data
| File | Right answer |
|---|---|
| `rfp/rfp_01_realtime_payments.txt` | **eng-01** (GCC, Kafka, core banking, batch window) |
| `rfp/rfp_02_regulatory_dora.txt` | **eng-07** (DORA, German lender) |
| `expected/librarian_expected.json` | the answer key |

If eng-01 isn't top for the payments RFP, it isn't working — say so honestly
rather than quietly rewording the question until it passes.
