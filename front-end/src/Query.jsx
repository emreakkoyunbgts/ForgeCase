import { useState } from 'react';
import { Link } from 'react-router-dom';
import { newTrace, request } from './api';
import './Workbench.css';

export default function Query() {
  const [query, setQuery] = useState('');
  const [matches, setMatches] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function search(event) {
    event.preventDefault(); if (!query.trim() || busy) return;
    setBusy(true); setError(''); setMatches(null);
    try {
      const { data } = await request('librarian', '/match', {
        method: 'POST', body: { rfp_text: query, top_k: 3 }, trace: newTrace(), timeout: 30000,
      });
      const selected = data.requirements.map(item => item.best_match).filter(Boolean);
      setMatches([...new Map(selected.map(item => [item.engagement_id, item])).values()]);
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  return <main className="workbench"><h1>Find a source</h1>
    <p>Search the Vault through Librarian, then choose one engagement for your case study.</p>
    <form className="work-panel" onSubmit={search}><label htmlFor="rfp">Requirements</label>
      <textarea id="rfp" rows={5} value={query} onChange={e => setQuery(e.target.value)} disabled={busy} />
      <button disabled={busy || !query.trim()}>{busy ? 'Searching…' : 'Find engagements'}</button></form>
    {error && <div className="message error" role="alert">{error}</div>}
    {matches?.length === 0 && <p role="status">No matching engagement found. You can still select a known record from the Workbench.</p>}
    {matches?.map(item => <section className="work-panel" key={item.engagement_id}>
      <h2>{item.engagement_id}</h2><Link to={'/engagements/' + encodeURIComponent(item.engagement_id)}>Use this source</Link>
    </section>)}
  </main>;
}
