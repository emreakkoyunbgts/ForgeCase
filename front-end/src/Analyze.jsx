import { useState } from "react";
import axios from "axios";
import "./Analyze.css";

const ANALYSIS_API_BASE_URL = "http://localhost:8006";

function getErrorMessage(error, fallback) {
  if (error.response?.data?.detail) return error.response.data.detail;
  return error.request ? "Could not connect to the backend." : fallback;
}

function Analyze() {
  const [coverage, setCoverage] = useState(null);
  const [gaps, setGaps] = useState(null);
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  const runAnalysis = async (type) => {
    setLoading(type);
    setError("");

    try {
      const response = await axios.get(`${ANALYSIS_API_BASE_URL}/${type}`);
      if (type === "coverage") setCoverage(response.data);
      else setGaps(response.data);
    } catch (err) {
      console.error(`Failed to analyze ${type}:`, err);
      setError(
        getErrorMessage(err, `The ${type} analysis could not be completed.`),
      );
    } finally {
      setLoading("");
    }
  };

  return (
    <div className="analyze-page">
      <div className="analyze-header">
        <h1>Analyze</h1>
        <p>
          Review record coverage and identify missing domain and region
          combinations.
        </p>
      </div>

      <div className="analyze-actions">
        <button onClick={() => runAnalysis("gaps")} disabled={Boolean(loading)}>
          {loading === "gaps" ? "Analyzing gaps..." : "Analyze Gap"}
        </button>
        <button
          className="secondary-button"
          onClick={() => runAnalysis("coverage")}
          disabled={Boolean(loading)}
        >
          {loading === "coverage"
            ? "Analyzing coverage..."
            : "Analyze Coverage"}
        </button>
      </div>

      {error && (
        <div className="analysis-error" role="alert">
          {error}
        </div>
      )}

      {coverage && (
        <section className="analysis-result" aria-live="polite">
          <h2>Coverage Analysis</h2>
          <div className="metrics-grid">
            <Metric label="Total engagements" value={coverage.total_engagements} />
            <Metric label="Domains" value={Object.keys(coverage.by_domain || {}).length} />
            <Metric label="Regions" value={Object.keys(coverage.by_region || {}).length} />
            <Metric label="Client types" value={Object.keys(coverage.by_client_type || {}).length} />
          </div>
          <div className="analysis-details">
            <CountList title="By domain" items={coverage.by_domain} />
            <CountList title="By region" items={coverage.by_region} />
          </div>
          <CountList title="By client type" items={coverage.by_client_type} />
          <MissingOutcomes items={coverage.no_outcome} />
        </section>
      )}

      {gaps && (
        <section className="analysis-result" aria-live="polite">
          <h2>Gap Analysis</h2>
          <div className="metrics-grid one-column">
            <Metric label="Total gaps" value={gaps.total_gaps} />
          </div>
          <GapTable items={gaps.gaps} />
        </section>
      )}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value ?? "—"}</strong>
    </div>
  );
}

function CountList({ title, items = {} }) {
  const entries = Object.entries(items || {});
  return (
    <div className="count-list">
      <h3>{title}</h3>
      {entries.length ? (
        <div>
          {entries.map(([name, count]) => (
            <span className="tag" key={name}>
              {name}: {count}
            </span>
          ))}
        </div>
      ) : (
        <p className="empty-text">No data available.</p>
      )}
    </div>
  );
}

function GapTable({ items = [] }) {
  return (
    <AnalysisTable title="Missing combinations" headers={["Domain", "Region"]}>
      {items.map((item, index) => (
        <tr key={`${item.domain}-${item.region}-${index}`}>
          <td>{item.domain}</td>
          <td>{item.region}</td>
        </tr>
      ))}
    </AnalysisTable>
  );
}

function AnalysisTable({ title, headers, children }) {
  const rowCount = Array.isArray(children) ? children.length : 0;
  return (
    <div className="analysis-table-wrap">
      <h3>{title}</h3>
      {rowCount ? (
        <table>
          <thead>
            <tr>
              {headers.map((header) => (
                <th key={header}>{header}</th>
              ))}
            </tr>
          </thead>
          <tbody>{children}</tbody>
        </table>
      ) : (
        <p className="empty-text">No items found.</p>
      )}
    </div>
  );
}

function MissingOutcomes({ items = [] }) {
  return (
    <div className="missing-outcomes">
      <h3>Engagements missing outcomes</h3>
      {items.length ? (
        <div>
          {items.map((id) => (
            <span className="tag" key={id}>
              {id}
            </span>
          ))}
        </div>
      ) : (
        <p className="empty-text">All engagements include outcomes.</p>
      )}
    </div>
  );
}

export default Analyze;
