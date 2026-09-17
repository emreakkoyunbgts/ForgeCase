# CaseForge

CaseForge turns a structured engagement closeout PDF into a case study grounded
in one Vault record. React and Streamlit provide the same English, German and
Turkish workflow: upload or select, generate, edit, verify, approve, publish,
and download a DOCX or PDF with provenance.

The CF-105 runtime transfers records and drafts over HTTP. Reader stores
extracted records in Vault; downstream services obtain source facts from Vault's
API. Local seed and corpus files are not substitutes for unavailable services.

## Get started

Use Python 3.11 and Node.js. From the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm --prefix front-end ci
```

Use an existing virtual environment when available. Copy `.env.example` to
`.env` only if it does not already exist. Set `OPENAI_API_KEY` locally; generation
and successful verification require the provider. Both model settings default
to `gpt-5.5`. Never commit secrets or put them in `VITE_*` variables.

Provision the Librarian model cache, then start seven real APIs and both UIs:

```powershell
python scripts/provision_librarian.py
python scripts/run_mesh.py --isolated --with-ui
```

Provisioning explicitly downloads embedding weights; requests do not.
`--isolated` uses temporary Vault/artifact stores removed at shutdown. Omit it
for storage configured by `CASEFORGE_VAULT_DB` and `CASEFORGE_ARTIFACT_DIR`.
Logs are in `out/logs/`; Ctrl+C stops the launcher's child processes.

Open **React: http://127.0.0.1:5173** or
**Streamlit: http://127.0.0.1:8501**. Upload a supported PDF first when using an
empty isolated Vault.

| Service | Default port | Main API |
|---|---|---|
| Vault | 8000 | `/engagements` |
| Generator | 8001 | `/generate` |
| Librarian | 8002 | `/search`, `/match` |
| Reader | 8003 | `/extract` |
| Verifier | 8004 | `/verify` |
| Publisher | 8005 | `/publish`, `/artifacts/{id}/download`, `/artifacts/{id}/provenance` |
| Analyst | 8007 | `/coverage`, `/gaps` |

Addresses come from `.env`; the local launcher requires loopback URLs without
path prefixes. Every API exposes `/health`, `/docs` and `/openapi.json`.

## Publication rules

Reader accepts text-layer closeouts with explicit required fields and Challenge
and Approach sections. Scans, broken PDFs and unsupported structure return
`422`. It does not infer absent facts through OCR or a model. Naming consent
starts false, and missing outcomes remain empty.

Every HTTP PASS requires an independent semantic comparison with the original
Vault record. Editing the source, language or draft invalidates UI verification
and approval. Publisher verifies final display content again and requires a
matching PASS with no problems before creating an artifact. Model failures and
unknown verdicts cannot authorize publication.

See the [CF-105 runbook](docs/CF-105-runbook.md) for supported PDF structure,
contracts, individual service commands, CLI usage, errors and release gates.

## Verification

```powershell
python -m pytest -q
npm --prefix front-end run build
npm --prefix front-end run lint
```

The default pytest selection is the isolated cutover suite in `pytest.ini`.
It uses synthetic records and injected providers. Historical archive-dependent
or real-model experiments are outside that selection and are not counted as
passing tests. Mock results do not establish model accuracy or live mesh
acceptance.

Against a new isolated production mesh with a real provider key, run:

```powershell
python scripts/live_acceptance.py --output out/acceptance/live.json
```

It evaluates 12 synthetic sources in three languages and labelled negative
examples. Missing credentials or failed expectations return exit code `2` with
recorded evidence. Both UI flows, outage handling and visual document review
remain separate gates. Create the annotated `cf-105-http-only` tag only when all
gates pass on the same clean commit.
