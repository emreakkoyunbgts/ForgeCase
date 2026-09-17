# Streamlit Console

Console provides the complete HTTP workflow in EN/DE/TR: upload/select a Vault
record → select language → generate → edit → verify → human approval → publish
→ download document and provenance.

Start the APIs with the [mesh launcher](../docs/CF-105-runbook.md), or start them
individually, then run from the repository root:

```powershell
python -m streamlit run console/console.py --server.address 127.0.0.1 --server.port 8501
```

Open http://127.0.0.1:8501. Configure service URLs and optional `CASEFORGE_TOKEN`
in the root `.env`. HTTP requests originate from the Streamlit server. Console
does not import Generator/Verifier business logic or read a corpus file.

Reader handles upload persistence. If `X-Vault-Stored` is false, extraction can
be inspected but generation cannot proceed. Edits, source changes and language
changes invalidate the current PASS and human approval. Approval is tied to the
record, language and draft content. A failed stage stops the workflow and shows
its correlation ID. Publisher verifies final content again before creating an
artifact, even when the interface has already displayed PASS.

DOCX and all three PDF layouts are downloaded as HTTP response bytes. Session
state belongs only to this interface and is not another service's data source.
The service-health control reports API availability, not semantic model accuracy.

Default synthetic tests and the offline UI harness do not replace real-provider
acceptance in both interfaces. Release requirements and supported input structure
are in the [CF-105 runbook](../docs/CF-105-runbook.md).
