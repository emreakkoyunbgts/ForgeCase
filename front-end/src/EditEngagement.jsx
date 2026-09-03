import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import "./EditEngagement.css";

const ENGAGEMENTS_API_BASE_URL = "http://localhost:8000";

function getErrorMessage(error, fallback) {
  if (error.response?.data?.detail) return error.response.data.detail;
  return error.request ? "Could not connect to the backend." : fallback;
}

function EditEngagement() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [record, setRecord] = useState(null);
  const [etag, setEtag] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const loadRecord = async () => {
      try {
        const response = await axios.get(`${ENGAGEMENTS_API_BASE_URL}/engagements/${id}`);
        setRecord(response.data);
        setEtag(response.headers.etag || null);
      } catch (err) {
        console.error("Error loading engagement for editing:", err);
        setError(getErrorMessage(err, "The engagement could not be loaded."));
      } finally {
        setLoading(false);
      }
    };

    loadRecord();
  }, [id]);

  const updateField = (field, value) => {
    setRecord((current) => ({ ...current, [field]: value }));
  };

  const updateOutcome = (index, field, value) => {
    setRecord((current) => ({
      ...current,
      outcomes: current.outcomes.map((outcome, outcomeIndex) =>
        outcomeIndex === index ? { ...outcome, [field]: value } : outcome
      ),
    }));
  };

  const addOutcome = () => {
    setRecord((current) => ({
      ...current,
      outcomes: [...current.outcomes, { metric: "", source_ref: "" }],
    }));
  };

  const removeOutcome = (index) => {
    setRecord((current) => ({
      ...current,
      outcomes: current.outcomes.filter((_, outcomeIndex) => outcomeIndex !== index),
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!record || saving) return;

    if (!etag) {
      setError("The record version could not be read. Refresh the page and try again.");
      return;
    }

    const payload = {
      ...record,
      technologies: (Array.isArray(record.technologies)
        ? record.technologies
        : (record.technologies || "").split(","))
        .map((technology) => technology.trim())
        .filter(Boolean),
      team_size: Number(record.team_size),
      duration_months: Number(record.duration_months),
    };

    setSaving(true);
    setError("");
    try {
      await axios.put(`${ENGAGEMENTS_API_BASE_URL}/engagements/${id}`, payload, {
        headers: { "If-Match": etag },
      });
      navigate(`/engagements/${id}`);
    } catch (err) {
      console.error("Error saving engagement:", err);
      setError(getErrorMessage(err, "The engagement could not be saved."));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div>Loading engagement...</div>;
  if (!record) return <div>{error || "Engagement not found."}</div>;

  return (
    <div className="edit-engagement-container">
      <div className="edit-engagement-header">
        <div>
          <h1>Edit Engagement</h1>
          <p>Update the record, then save your changes.</p>
        </div>
        <button type="button" className="cancel-button" onClick={() => navigate(`/engagements/${id}`)} disabled={saving}>
          Cancel
        </button>
      </div>

      <form className="edit-engagement-form" onSubmit={handleSubmit}>
        {error && <div className="edit-error" role="alert">{error}</div>}

        <label>
          ID
          <input value={record.id} disabled />
        </label>
        <label>
          Client
          <input value={record.client || ""} onChange={(event) => updateField("client", event.target.value)} required />
        </label>
        <label>
          Client Type
          <input value={record.client_type || ""} onChange={(event) => updateField("client_type", event.target.value)} required />
        </label>
        <label>
          Domain
          <input value={record.domain || ""} onChange={(event) => updateField("domain", event.target.value)} required />
        </label>
        <label>
          Region
          <select value={record.region || ""} onChange={(event) => updateField("region", event.target.value)} required>
            <option value="">Select a region</option>
            <option value="UK">UK</option>
            <option value="DE">DE</option>
            <option value="NL">NL</option>
            <option value="TR">TR</option>
            <option value="GCC">GCC</option>
          </select>
        </label>
        <label className="checkbox-label">
          <input type="checkbox" checked={Boolean(record.may_be_named)} onChange={(event) => updateField("may_be_named", event.target.checked)} />
          May be named
        </label>
        <label className="full-width">
          Challenge
          <textarea rows="4" value={record.challenge || ""} onChange={(event) => updateField("challenge", event.target.value)} required />
        </label>
        <label className="full-width">
          Solution
          <textarea rows="4" value={record.solution || ""} onChange={(event) => updateField("solution", event.target.value)} required />
        </label>
        <label className="full-width">
          Technologies <span>Comma-separated</span>
          <input value={Array.isArray(record.technologies) ? record.technologies.join(", ") : record.technologies || ""} onChange={(event) => updateField("technologies", event.target.value)} />
        </label>
        <label>
          Team Size
          <input type="number" min="1" value={record.team_size ?? ""} onChange={(event) => updateField("team_size", event.target.value)} required />
        </label>
        <label>
          Duration (Months)
          <input type="number" min="1" value={record.duration_months ?? ""} onChange={(event) => updateField("duration_months", event.target.value)} required />
        </label>

        <section className="outcomes-editor full-width">
          <div className="outcomes-editor-header">
            <h2>Outcomes</h2>
            <button type="button" className="secondary-button" onClick={addOutcome} disabled={saving}>Add Outcome</button>
          </div>
          {record.outcomes.map((outcome, index) => (
            <div className="outcome-editor" key={index}>
              <label>
                Metric
                <input value={outcome.metric || ""} onChange={(event) => updateOutcome(index, "metric", event.target.value)} required />
              </label>
              <label>
                Source Reference
                <input value={outcome.source_ref || ""} onChange={(event) => updateOutcome(index, "source_ref", event.target.value)} required />
              </label>
              <button type="button" className="remove-outcome-button" onClick={() => removeOutcome(index)} disabled={saving}>Remove</button>
            </div>
          ))}
        </section>

        <div className="edit-actions full-width">
          <button type="button" className="cancel-button" onClick={() => navigate(`/engagements/${id}`)} disabled={saving}>Cancel</button>
          <button type="submit" className="save-button" disabled={saving}>{saving ? "Saving..." : "Save Changes"}</button>
        </div>
      </form>
    </div>
  );
}

export default EditEngagement;
