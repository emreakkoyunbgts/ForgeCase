# Reader

Reader turns a supported text-layer closeout PDF into an Engagement Record and
stores it through Vault HTTP. It is the only writer in the supported upload
workflow; interfaces do not repeat the Vault POST.

```powershell
python -m uvicorn reader.api:create_app --factory --host 127.0.0.1 --port 8003
```

`POST /extract` accepts multipart field `document` (maximum 20 MiB). Required
facts are Engagement ID, client, client type, domain, region, Challenge and
Approach. Technologies come from their explicit list; outcomes come from their
section and retain actual filename/page references. No outcomes means an empty
list. Naming consent defaults to false regardless of the name in the document.

Missing/conflicting required fields, scans, invalid PDFs and unsupported layout
return `422`. This production endpoint does not run OCR or infer facts with an
LLM. `reader/layout.py` handles labelled fields, numbered sections, columns and
supported tables. See [the supported document example](../docs/CF-105-runbook.md#reader-documents-and-storage).

The response contains the extracted record and `X-Vault-Stored` /
`X-Vault-Detail` headers. Extraction may succeed while persistence is unconfirmed;
generation must remain unavailable until storage is confirmed. `?store=false`
extracts without storing. After an uncertain create or conflict, Reader reads
the same ID, accepts equal content, rejects different content, and makes at most
one further write after 0.5 seconds if the ID is absent.

`VAULT_URL`, authorization and correlation headers follow the
[shared runbook](../docs/CF-105-runbook.md). CLI upload also uses HTTP:

```powershell
python -m reader.reader reader/fixtures/two_column_closeout.pdf
```

`--text-only` and `--layout` are local inspection tools, not the production
extraction contract. Existing layout fixtures are committed in `reader/fixtures`.
The default isolated suite contains CF-105 extraction and storage-reconciliation
tests; historical archive/OCR tests are not release acceptance.
