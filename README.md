# CaseForge

An internal tool that turns a completed BGTS engagement into a polished,
**grounded** case study — one where every claim can be traced back to the
source document, and nothing is ever invented.

Built by the 2026 intern cohort. Eight people, eight programs, one pipeline.

---

## The rule

> **CaseForge never invents a fact.**
> If it is not in the source document, it does not go in the output.
> Where a fact is missing we say so — we never guess.

Everything in this repo follows from that.

---

## Get started (10 minutes)

```bash
# 1. clone, then create a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. install
pip install -r requirements.txt

# 3. unzip the test data into this folder
#    you should end up with:  caseforge/caseforge-testdata/

# 4. check everything works
python -m pytest -q

# 5. RUN THE WHOLE PIPELINE (it already works, using stubs)
bash scripts/run_pipeline.sh
```

That last command runs all eight programs end to end and produces a PDF.
It works **today**, before anyone has written any real code, because every
program starts as a stub that returns seed data.

**Your job is to replace your stub with a real implementation.**

---

## Who owns what

| Folder | Prototype | Owner |
|---|---|---|
| `reader/` | Document → Engagement Record | Çağrı |
| `vault/` | Store + REST API | Kaan |
| `generator/` | Record → grounded case study | Taha |
| `verifier/` | Catches invented facts — **the gate** | Ömer |
| `publisher/` | Case study → branded PDF | Ahmet |
| `librarian/` | RFP → best-matching engagements | Arda |
| `analyst/` | Coverage & gap analysis | Elif |
| `console/` | The web app over everything | Serhat |
| `common/` | Shared code — **everybody** | (change with care) |

Find your folder. Open its `README.md`. Start there.

---

## Ground rules

- Never commit secrets. Copy `.env.example` to `.env` and put your key there.
  `.env` is gitignored.
- Never modify `caseforge-testdata/` — it is the fixed thing we all test against.
- Never change `common/contract.py` alone. It is the shared contract; changing it
  breaks everyone. Propose it in standup first.
- One branch per Jira ticket. One pull request. At least one reviewer.

See the **Project Specification** for the normative rules.
