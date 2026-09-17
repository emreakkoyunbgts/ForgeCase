import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { describeError, newTrace, request } from './api';
import { REGIONS, readETag, validRecordId, validateRecord } from './contracts';
import './EditEngagement.css';

const TEXT_FIELDS = [['client', 'Client'], ['client_type', 'Client type'], ['domain', 'Domain']];
const LONG_FIELDS = [['challenge', 'Challenge'], ['solution', 'Solution']];

// Outcome rows need a key that survives a removal, so identity is tracked
// alongside the values instead of by array index.
let nextKey = 0;
const keyed = outcomes => outcomes.map(outcome => ({ key: `outcome-${nextKey++}`, ...outcome }));
const bare = outcome => ({ metric: outcome.metric, source_ref: outcome.source_ref });

export default function EditEngagement() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [record, setRecord] = useState(null);
  const [outcomes, setOutcomes] = useState([]);
  const [technologies, setTechnologies] = useState('');
  const [etag, setEtag] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const trace = useRef(newTrace());

  useEffect(() => {
    let live = true;
    async function load() {
      try {
        const { data, headers } = await request('vault', `/engagements/${encodeURIComponent(id)}`,
          { trace: trace.current });
        if (!live) return;
        const valid = validateRecord(data);
        setRecord(valid);
        setOutcomes(keyed(valid.outcomes));
        setTechnologies(valid.technologies.join(', '));
        setEtag(readETag(headers));
      } catch (failure) {
        if (live) setError(describeError(failure.detail) || failure.message);
      } finally {
        if (live) setLoading(false);
      }
    }
    if (!validRecordId(id)) {
      setError('That engagement id is not valid.');
      setLoading(false);
      return undefined;
    }
    load();
    return () => { live = false; };
  }, [id]);

  function field(name, value) { setRecord(current => ({ ...current, [name]: value })); }
  function editOutcome(key, name, value) {
    setOutcomes(current => current.map(item => (item.key === key ? { ...item, [name]: value } : item)));
  }

  async function submit(event) {
    event.preventDefault();
    if (!record || saving) return;
    if (!etag) {
      setError('This record has no version tag, so it cannot be saved safely. Reload the page and try again.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await request('vault', `/engagements/${encodeURIComponent(id)}`, {
        method: 'PUT',
        trace: trace.current,
        headers: { 'If-Match': etag },
        body: {
          ...record,
          technologies: technologies.split(',').map(item => item.trim()).filter(Boolean),
          outcomes: outcomes.map(bare),
          team_size: Number(record.team_size) || null,
          duration_months: Number(record.duration_months) || null,
        },
      });
      navigate(`/engagements/${encodeURIComponent(id)}`);
    } catch (failure) {
      // 412 is the vault concurrency gate, not a validation problem.
      setError(failure.status === 412
        ? 'Someone else changed this record while you were editing. Reload to see their version.'
        : describeError(failure.detail) || failure.message);
      setSaving(false);
    }
  }

  if (loading) return <div className="edit-engagement-container">Loading engagement…</div>;
  if (!record) {
    return <div className="edit-engagement-container" role="alert">{error || 'Engagement not found.'}</div>;
  }

  return <div className="edit-engagement-container">
    <header className="edit-engagement-header">
      <h1>Edit engagement</h1>
      <p>Update the record, then save. The vault refuses the save if someone else changed it first.</p>
    </header>

    <form className="edit-engagement-form" onSubmit={submit}>
      {error && <div className="edit-error" role="alert">{error}</div>}

      <label>ID<input value={record.id} disabled /></label>
      {TEXT_FIELDS.map(([name, label]) => <label key={name}>
        {label}
        <input value={record[name]} onChange={event => field(name, event.target.value)} required />
      </label>)}
      <label>
        Region
        <select value={record.region} onChange={event => field('region', event.target.value)} required>
          {REGIONS.map(region => <option key={region} value={region}>{region}</option>)}
        </select>
      </label>
      <label className="checkbox-label">
        <input type="checkbox" checked={record.may_be_named}
               onChange={event => field('may_be_named', event.target.checked)} />
        The client may be named
      </label>
      {LONG_FIELDS.map(([name, label]) => <label className="full-width" key={name}>
        {label}
        <textarea rows="4" value={record[name]} onChange={event => field(name, event.target.value)} required />
      </label>)}
      <label className="full-width">
        Technologies <span>Comma separated</span>
        <input value={technologies} onChange={event => setTechnologies(event.target.value)} />
      </label>
      <label>
        Team size
        <input type="number" min="1" value={record.team_size ?? ''}
               onChange={event => field('team_size', event.target.value)} />
      </label>
      <label>
        Duration (months)
        <input type="number" min="1" value={record.duration_months ?? ''}
               onChange={event => field('duration_months', event.target.value)} />
      </label>

      <section className="outcomes-editor full-width">
        <div className="outcomes-editor-header">
          <h2>Outcomes</h2>
          <button type="button" className="secondary-button" disabled={saving}
                  onClick={() => setOutcomes(current => [...current, ...keyed([{ metric: '', source_ref: '' }])])}>
            Add outcome
          </button>
        </div>
        {outcomes.length ? outcomes.map(item => <div className="outcome-editor" key={item.key}>
          <label>
            Metric
            <input value={item.metric} required
                   onChange={event => editOutcome(item.key, 'metric', event.target.value)} />
          </label>
          <label>
            Source reference
            <input value={item.source_ref} required
                   onChange={event => editOutcome(item.key, 'source_ref', event.target.value)} />
          </label>
          <button type="button" className="remove-outcome-button" disabled={saving}
                  onClick={() => setOutcomes(current => current.filter(row => row.key !== item.key))}>
            Remove
          </button>
        </div>) : <p className="empty-text">No outcomes yet. A case study needs at least one.</p>}
      </section>

      <div className="edit-actions full-width">
        <button type="button" className="cancel-button" disabled={saving}
                onClick={() => navigate(`/engagements/${encodeURIComponent(id)}`)}>
          Cancel
        </button>
        <button type="submit" className="save-button" disabled={saving}>
          {saving ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </form>
  </div>;
}
