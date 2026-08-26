import { useState } from "react";
import axios from "axios";
import "./Query.css";

function Query() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleGenerate = async () => {
    if (!query.trim()) {
      setError("Please enter a query.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await axios.post(
        "http://localhost:8001/generator/mcs/query",
        null,
        {
          params: {
            query: query.trim(),
          },
        }
      );

      setResult(response.data);
    } catch (err) {
      console.error(err);

      if (err.response) {
        setError(
          `Backend error: ${err.response.status} - ${
            err.response.data?.detail || "Unknown error"
          }`
        );
      } else {
        setError("Could not connect to the backend.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="query-page">
      <div className="query-container">

        {/* Header */}
        <div className="page-header">
          <h1>Multi-Source Content Generator</h1>
          <p>
            Enter a query to find the most relevant engagement and generate
            multi-source content.
          </p>
        </div>

        {/* Query Input */}
        <div className="query-box">
          <input
            type="text"
            placeholder="Enter your query..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                handleGenerate();
              }
            }}
          />

          <button
            onClick={handleGenerate}
            disabled={loading}
          >
            {loading ? "Generating..." : "Generate MCS"}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="error-box">
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="loading-box">
            <div className="spinner"></div>
            <p>Generating multi-source content...</p>
          </div>
        )}

        {/* Result */}
        {result && !loading && (
          <div className="mcs-result">

            {/* Engagement Header */}
            <div className="result-header">
              <div>
                <span className="result-label">ENGAGEMENT</span>

                <h2>
                  {result.titles?.[0]?.title || "Generated Engagement"}
                </h2>
              </div>

              <div className="engagement-id">
                {result.engagement_ids?.join(", ")}
              </div>
            </div>

            {/* Sections */}
            <div className="sections-grid">

              {/* Context */}
              <Section
                title="Context"
                items={result.sections?.context}
                field="region"
              />

              {/* Challenge */}
              <Section
                title="Challenge"
                items={result.sections?.challenge}
                field="challenge"
              />

              {/* Approach */}
              <Section
                title="Approach"
                items={result.sections?.approach}
                field="approach"
              />

              {/* Technology */}
              <Section
                title="Technology"
                items={result.sections?.technology}
                field="technologies"
              />

              {/* Outcomes */}
              <Section
                title="Outcomes"
                items={result.sections?.outcomes}
                field="outcomes"
              />

            </div>

            {/* Citations */}
            {result.citations?.length > 0 && (
              <div className="citations-card">
                <h3>Citations</h3>

                <div className="citations-list">
                  {result.citations.map((citation, index) => (
                    <div
                      className="citation-item"
                      key={index}
                    >
                      <div className="citation-claim">
                        {citation.claim}
                      </div>

                      <div className="citation-source">
                        <span>
                          Source: {citation.source_ref}
                        </span>

                        <span>
                          Page: {citation.page_ref}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Metadata */}
            <div className="metadata-card">
              <div className="metadata-item">
                <span>Client Named</span>
                <strong>
                  {result.client_named ? "Yes" : "No"}
                </strong>
              </div>

              <div className="metadata-item">
                <span>Engagement ID</span>
                <strong>
                  {result.engagement_ids?.join(", ") || "-"}
                </strong>
              </div>

              <div className="metadata-item">
                <span>Sources</span>
                <strong>
                  {result.citations?.length || 0}
                </strong>
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
}


/*
 * Reusable section component
 */
function Section({ title, items, field }) {
  if (!items || items.length === 0) {
    return null;
  }

  return (
    <div className="section-card">

      <div className="section-title">
        <h3>{title}</h3>
      </div>

      <div className="section-content">
        {items.map((item, index) => (
          <div
            className="section-item"
            key={index}
          >
            <p>{item[field]}</p>

            {item.page && (
              <span className="page-reference">
                {item.page}
              </span>
            )}
          </div>
        ))}
      </div>

    </div>
  );
}

export default Query;