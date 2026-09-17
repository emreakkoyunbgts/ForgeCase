# CaseForge React interface

The React/Vite interface provides upload/select → EN/DE/TR generation → editing
→ verification → human approval → publication → document/provenance download.
Librarian search can choose one Vault source. Changing source, language or draft
invalidates prior PASS and approval; Publisher independently verifies the final
content again.

From the repository root:

```powershell
npm --prefix front-end ci
npm --prefix front-end run dev -- --host 127.0.0.1 --port 5173
```

Open http://127.0.0.1:5173 with the seven APIs running. Alternatively,
`python scripts/run_mesh.py --isolated --with-ui` starts all APIs and both UIs.

The browser uses relative `/api/{service}/...` URLs. `vite.config.js` reads base
URLs and optional `CASEFORGE_TOKEN` from the root environment and adds the token
on the server side. Never put secrets in `VITE_*` variables. The proxy has an
explicit service allowlist; API errors preserve correlation IDs for diagnosis.
A static deployment requires an equivalent server-side proxy: copying `dist/`
alone does not start the APIs or provide authentication forwarding.

Reader uploads must report confirmed Vault storage before generation becomes
available. Duplicate in-flight actions are prevented. Downloads fetch actual
Publisher bytes and provenance over HTTP, not a server filesystem path.

```powershell
npm --prefix front-end run build
npm --prefix front-end run lint
```

These checks validate build/lint behavior, not real model accuracy or completed
browser acceptance. See the [CF-105 runbook](../docs/CF-105-runbook.md) for API
ports, credentials, supported document structure and release gates.
