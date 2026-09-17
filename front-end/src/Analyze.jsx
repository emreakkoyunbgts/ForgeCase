import { useState } from 'react';
import { describeError, newTrace, request } from './api';
import { validateCoverage, validateGaps } from './contracts';
import './Analyze.css';

const REPORTS = {
  coverage: { path: '/coverage', validate: validateCoverage, label: 'coverage' },
  gaps: { path: '/gaps', validate: validateGaps, label: 'gap' },
};

export default function Analyze() {
  const [coverage, setCoverage] = useState(null);
  const [gaps, setGaps] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  async function run(name) {
    const report = REPORTS[name];
    setBusy(name);
    setError('');
    try {
      const { data } = await request('analyst', report.path, { trace: newTrace() });
      const validated = report.validate(data);
      if (name === 'coverage') setCoverage(validated); else setGaps(validated);
    } catch (failure) {
      setError(describeError(failure.detail) || failure.message ||
        `The ${report.label} analysis could not be completed.`);
    } finally {
      setBusy('');
    }
  }

  return <div className="analyze-page">
    <header className="analyze-header">
      <h1>Analyze</h1>
      <p>Review record coverage and find domain and region combinations with no engagement behind them.</p>
    </header>

    <div className="analyze-actions">
      <button onClick={() => run('gaps')} disabled={Boolean(busy)}>
        {busy === 'gaps' ? 'Analysing gaps…' : 'Analyse gaps'}
      </button>
      <button className="secondary-button" onClick={() => run('coverage')} disabled={Boolean(busy)}>
        {busy === 'coverage' ? 'Analysing coverage…' : 'Analyse coverage'}
      </button>
    </div>

    {error && <div className="analysis-error" role="alert">{error}</div>}

    {coverage && <section className="analysis-result" aria-live="polite">
      <h2>Coverage</h2>
      <div className="metrics-grid">
        <Metric label="Total engagements" value={coverage.total_engagements} />
        <Metric label="Domains" value={Object.keys(coverage.by_domain).length} />
        <Metric label="Regions" value={Object.keys(coverage.by_region).length} />
        <Metric label="Client types" value={Object.keys(coverage.by_client_type).length} />
      </div>
      <div className="analysis-details">
        <CountList title="By domain" items={coverage.by_domain} />
        <CountList title="By region" items={coverage.by_region} />
        <CountList title="By client type" items={coverage.by_client_type} />
      </div>
      <TagList title="Engagements missing outcomes" items={coverage.no_outcome}
               empty="Every engagement records at least one outcome." />
    </section>}

    {gaps && <section className="analysis-result" aria-live="polite">
      <h2>Gaps</h2>
      <div className="metrics-grid one-column">
        <Metric label="Total gaps" value={gaps.total_gaps} />
      </div>
      <div className="analysis-table-wrap">
        {gaps.gaps.length ? <table>
          <caption>Domain and region combinations with no engagement</caption>
          <thead><tr><th scope="col">Domain</th><th scope="col">Region</th></tr></thead>
          <tbody>
            {gaps.gaps.map(gap => <tr key={`${gap.domain}/${gap.region}`}>
              <td>{gap.domain}</td><td>{gap.region}</td>
            </tr>)}
          </tbody>
        </table> : <p className="empty-text">No gaps: every domain is covered in every region.</p>}
      </div>
    </section>}
  </div>;
}

function Metric({ label, value }) {
  return <div className="metric-card"><span>{label}</span><strong>{value ?? '—'}</strong></div>;
}

function CountList({ title, items }) {
  const entries = Object.entries(items);
  return <div className="count-list">
    <h3>{title}</h3>
    {entries.length
      ? <div>{entries.map(([name, count]) => <span className="tag" key={name}>{name}: {count}</span>)}</div>
      : <p className="empty-text">No data available.</p>}
  </div>;
}

function TagList({ title, items, empty }) {
  return <div className="tag-list">
    <h3>{title}</h3>
    {items.length
      ? <div>{items.map(id => <span className="tag" key={id}>{id}</span>)}</div>
      : <p className="empty-text">{empty}</p>}
  </div>;
}
