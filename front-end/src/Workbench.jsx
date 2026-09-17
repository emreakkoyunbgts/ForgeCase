import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { describeError, downloadArtifact, newTrace, request } from './api';
import { FIELDS, hasVerifiedDraft, validRecordId, validateArtifact, validateDraft, validateRecordList, validateReport, workflowSignature } from './contracts';
import './Workbench.css';

const SERVICES = ['reader', 'vault', 'generator', 'verifier', 'publisher', 'librarian', 'analyst'];

export default function Workbench() {
  const { id: routeId } = useParams();
  const [records, setRecords] = useState([]);
  const [recordId, setRecordId] = useState(routeId || '');
  const [language, setLanguage] = useState('en');
  const [file, setFile] = useState(null);
  const [draft, setDraft] = useState(null);
  const [report, setReport] = useState(null);
  const [approved, setApproved] = useState(null);
  const [artifact, setArtifact] = useState(null);
  const [format, setFormat] = useState('docx');
  const [layout, setLayout] = useState('full-case-study');
  const [trace, setTrace] = useState(newTrace);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [extracted, setExtracted] = useState(null);
  const [health, setHealth] = useState({});
  const inFlight = useRef(false);
  const previousRoute = useRef(routeId);
  const signature = workflowSignature(recordId, language, draft);
  const verified = hasVerifiedDraft(report, signature, recordId);

  function invalidate() { setReport(null); setApproved(null); setArtifact(null); }
  function selectRecord(value) {
    setRecordId(value); setDraft(null); invalidate(); setTrace(newTrace()); setError(''); setNotice(''); setExtracted(null);
  }
  async function loadRecords(requestTrace = trace) {
    const { data } = await request('vault', '/engagements', { trace: requestTrace });
    setRecords(validateRecordList(data).items);
  }
  useEffect(() => { loadRecords().catch(err => setError(err.message)); }, []);
  useEffect(() => {
    if (previousRoute.current === routeId) return;
    previousRoute.current = routeId;
    setRecordId(routeId || ''); setDraft(null); setReport(null); setApproved(null); setArtifact(null);
    setTrace(newTrace()); setError(''); setNotice(''); setExtracted(null);
  }, [routeId]);

  async function run(step, action) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(step); setError('');
    try { await action(); } catch (err) { setError(err.message || describeError(err.detail)); }
    finally { inFlight.current = false; setBusy(''); }
  }

  function upload() {
    if (!file) return;
    run('Extracting and storing', async () => {
      setDraft(null); invalidate(); setRecordId(''); setNotice(''); setExtracted(null);
      const nextTrace = newTrace(); setTrace(nextTrace);
      const form = new FormData(); form.append('document', file);
      const result = await request('reader', '/extract', { method: 'POST', body: form, trace: nextTrace });
      setExtracted(result.data);
      if (!validRecordId(result.data?.id)) throw new Error('Reader returned an invalid engagement record');
      if (result.headers.get('X-Vault-Stored') !== 'true') {
        setNotice(`Extracted ${result.data.id}, but storage was not confirmed. ${result.headers.get('X-Vault-Detail') || ''}`);
        return;
      }
      await loadRecords(nextTrace);
      setRecordId(result.data.id); setNotice(`Stored ${result.data.id} in Vault.`);
    });
  }
  function generate() {
    run('Generating', async () => {
      setDraft(null); invalidate();
      const { data } = await request('generator', '/generate', {
        method: 'POST', body: { record_id: recordId, language }, trace,
      });
      setDraft(validateDraft(data, recordId, language));
    });
  }
  function updateText(section, index, field, text) {
    const copy = structuredClone(draft);
    const target = section === 'titles' ? copy.titles : copy.sections[section];
    target[index][field] = text;
    setDraft(copy); invalidate();
  }
  function verify() {
    run('Verifying', async () => {
      invalidate();
      const { data } = await request('verifier', '/verify', {
        method: 'POST', body: { record_id: recordId, draft, language }, trace,
      });
      setReport({ ...validateReport(data, recordId), signature });
    });
  }
  function publish() {
    if (!verified || approved !== signature) return;
    run('Publishing', async () => {
      setArtifact(null);
      const { data } = await request('publisher', '/publish', {
        method: 'POST', body: { record_id: recordId, draft, language, format, layout }, trace,
      });
      setArtifact(validateArtifact(data, format));
    });
  }
  function refreshHealth() {
    run('Checking services', async () => {
      const results = await Promise.all(SERVICES.map(async name => {
        try { await request(name, '/health', { trace, timeout: 3000 }); return [name, 'Available']; }
        catch { return [name, 'Unavailable']; }
      }));
      setHealth(Object.fromEntries(results));
    });
  }
  const record = records.find(item => item.id === recordId);
  return <main className="workbench">
    <header><p className="eyebrow">CASEFORGE</p><h1>Create a grounded case study</h1>
      <p>Choose a source, review the draft and publish only after verification.</p></header>
    {error && <div role="alert" className="message error">{error}</div>}
    {notice && <div role="status" className="message">{notice}</div>}
    {extracted && <details className="message" open={!recordId}><summary>Extracted engagement record</summary>
      <pre className="extraction-result">{JSON.stringify(extracted, null, 2)}</pre></details>}
    <section className="work-panel"><h2>1. Source</h2>
      <div className="work-grid">
        <div><label htmlFor="record-select">Engagement in Vault</label>
          <select id="record-select" value={recordId} disabled={!!busy} onChange={e => selectRecord(e.target.value)}>
            <option value="">Choose an engagement</option>
            {routeId && !records.some(item => item.id === routeId) && <option value={routeId}>{routeId}</option>}
            {records.map(item => <option key={item.id} value={item.id}>{item.id} — {item.client_type}</option>)}
          </select><button className="secondary" disabled={!!busy} onClick={() => run('Refreshing', loadRecords)}>Refresh records</button></div>
        <div><label htmlFor="pdf-upload">Or upload a structured closeout PDF</label>
          <input id="pdf-upload" type="file" accept="application/pdf" disabled={!!busy} onChange={e => setFile(e.target.files?.[0] || null)} />
          <small>Text-layer PDF with an Engagement ID, labelled fields and numbered sections.</small>
          <button disabled={!file || !!busy} onClick={upload}>Extract and store</button></div>
      </div>
      {record && <p className="source-summary">{record.may_be_named ? record.client : record.client_type} · {record.domain} · {record.region}
        {!record.may_be_named && <span className="badge">Anonymous client</span>}</p>}
    </section>
    <section className="work-panel"><h2>2. Draft</h2><div className="toolbar">
      <label htmlFor="language">Language</label>
      <select id="language" value={language} disabled={!!busy} onChange={e => { setLanguage(e.target.value); setDraft(null); invalidate(); }}>
        <option value="en">English</option><option value="de">Deutsch</option><option value="tr">Türkçe</option>
      </select><button disabled={!recordId || !!busy} onClick={generate}>Generate draft</button>
    </div>
    {draft && <div className="draft-editor">
      {draft.titles?.map((item, i) => <label key={`title-${i}`}>Title
        <input value={item.title} disabled={!!busy} onChange={e => updateText('titles', i, 'title', e.target.value)} /></label>)}
      {Object.entries(FIELDS).map(([section, field]) => draft.sections[section]?.map((item, i) =>
        <label key={`${section}-${i}`}>{section[0].toUpperCase() + section.slice(1)}
          <textarea rows={section === 'context' ? 2 : 4} value={item[field]} disabled={!!busy}
            onChange={e => updateText(section, i, field, e.target.value)} /></label>))}
      <details><summary>Source references</summary><ul>{draft.citations?.map((item, i) =>
        <li key={i}>{item.claim} <small>{item.source_ref}</small></li>)}</ul></details>
    </div>}</section>
    <section className="work-panel"><h2>3. Verify and approve</h2>
      <button disabled={!draft || !!busy} onClick={verify}>Verify draft</button>
      {report && <div className={`message ${verified ? 'success' : 'error'}`} role="status">
        <strong>{report.verdict}</strong>{report.problems.length > 0 && <ul>{report.problems.map((problem, i) =>
          <li key={i}>{describeError(problem)}{problem.value ? ` — ${describeError(problem.value)}` : ''}</li>)}</ul>}</div>}
      <label className="approval"><input type="checkbox" disabled={!verified || !!busy}
        checked={approved === signature && verified} onChange={e => setApproved(e.target.checked ? signature : null)} />
        I have reviewed this draft and approve publication.</label>
      <small>Editing the draft or changing its language clears verification and approval.</small>
    </section>
    <section className="work-panel"><h2>4. Publish and download</h2><div className="toolbar">
      <label htmlFor="format">Format</label><select id="format" value={format} disabled={!!busy}
        onChange={e => { setFormat(e.target.value); setLayout('full-case-study'); setArtifact(null); }}>
        <option value="docx">DOCX</option><option value="pdf">PDF</option></select>
      {format === 'pdf' && <><label htmlFor="layout">Layout</label><select id="layout" value={layout} disabled={!!busy}
        onChange={e => { setLayout(e.target.value); setArtifact(null); }}><option value="full-case-study">Full case study</option>
        <option value="one-pager">One pager</option><option value="single-slide">Single slide</option></select></>}
      <button disabled={!verified || approved !== signature || !!busy} onClick={publish}>Publish document</button>
    </div>
    {artifact && <div className="message success"><p>Ready: {artifact.filename}</p>
      <button disabled={!!busy} onClick={() => run('Downloading', () => downloadArtifact(artifact, trace))}>Download {format.toUpperCase()}</button>
      <button className="secondary" disabled={!!busy} onClick={() => run('Downloading provenance', () => downloadArtifact(artifact, trace, true))}>Download provenance</button></div>}
    </section>
    <footer><p role="status" aria-live="polite">{busy ? `${busy}…` : 'Ready'}</p>
      <small>Correlation ID: <code>{trace}</code></small>
      <details><summary>Service availability</summary><button disabled={!!busy} onClick={refreshHealth}>Check services</button>
        <ul>{SERVICES.map(name => <li key={name}>{name}: {health[name] || 'Not checked'}</li>)}</ul></details>
    </footer>
  </main>;
}
