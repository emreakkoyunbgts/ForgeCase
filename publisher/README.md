# Publisher

Publisher independently verifies final display content before creating a branded
DOCX/PDF and provenance sidecar. It reads the source from Vault HTTP and returns
artifact download URLs; no source corpus or seed fallback is used.

```powershell
python -m uvicorn publisher.service:app --host 127.0.0.1 --port 8005
```

`POST /publish` accepts `{record_id, draft, language, format, layout}`. Defaults
are `en`, `docx` and `full-case-study`. The draft must identify that same source
and language. It is converted to final display content before calling Verifier;
no translation, anonymization rewrite or other prose changes happen after PASS.

Publisher requires a matching source ID, `PASS`, and an empty problem list.
A BLOCK returns `422`. Unknown decisions, malformed responses, identity mismatch
and dependency/model failures return errors and create no artifact. A prior UI
PASS does not replace this final check.

Successful publication returns HTTP `201` with `artifact_id`, `filename`,
`media_type`, `download_url`, and `provenance_url`. Fetch the document from
`/artifacts/{id}/download` and JSON sidecar from `/artifacts/{id}/provenance`.
Use the applicable authorization header for both. URLs never expose server
filesystem paths. The server generates artifact IDs.

| Format/layout | Presentation |
|---|---|
| DOCX / full-case-study | Packaged Word template |
| PDF / full-case-study | Detailed portrait document, potentially multiple pages |
| PDF / one-pager | Compact portrait layout |
| PDF / single-slide | Landscape slide layout |

DOCX rejects non-default layouts. Headings are localized in EN/DE/TR, while
source references and machine metadata remain stable. The packaged template and
licensed DejaVu fonts live in `publisher/assets/`; missing assets cause startup
failure. PDFs embed Unicode fonts. Runtime rendering does not depend on fonts
installed on the host.

`CASEFORGE_ARTIFACT_DIR` configures private output storage. Tests and acceptance
use temporary stores. `VAULT_URL` and `VERIFIER_URL` configure dependencies;
Verifier calls allow time for its 60-second model assessment.

Documents include provenance: source IDs/references, SHA-256 content hash,
freshness, completion date when present, and evaluation date. Freshness uses
six calendar months. Missing/invalid dates yield `UNKNOWN`; no date is guessed.
This freshness status is separate from the mandatory Verifier PASS decision.
The machine sidecar is downloaded over HTTP.

The supported end-to-end CLI is:

```powershell
python -m integration.one_flow --record-id eng-01 --language tr --approve --format pdf --layout one-pager --out out/eng-01-tr.pdf
```

That output path receives HTTP-downloaded bytes. See the
[runbook](../docs/CF-105-runbook.md) for interactive review and acceptance.
Default tests exercise real rendering with injected semantic providers.
Historical `publisher/test_publisher.py` relies on older direct APIs and external
archive fixtures; it is not selected as default cutover acceptance.
