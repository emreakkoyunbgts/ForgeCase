import { useState } from "react";
import axios from "axios";
import "./UploadRecord.css";

const EXTRACT_API_BASE_URL = "http://localhost:8004";
const ENGAGEMENTS_API_BASE_URL = "http://localhost:8000";

function getErrorMessage(error, fallback) {
  if (error.response?.data?.detail) return error.response.data.detail;
  return error.request ? "Could not connect to the backend." : fallback;
}

function isPdf(file) {
  return file?.type === "application/pdf" || file?.name?.toLowerCase().endsWith(".pdf");
}

function UploadRecord() {
  const [file, setFile] = useState(null);
  const [record, setRecord] = useState(null);
  const [extracting, setExtracting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const handleFileChange = (event) => {
    const selectedFile = event.target.files?.[0] || null;
    setRecord(null);
    setSuccess("");

    if (selectedFile && !isPdf(selectedFile)) {
      setFile(null);
      setError("Only PDF files can be uploaded.");
      event.target.value = "";
      return;
    }

    setFile(selectedFile);
    setError("");
  };

  const handleExtract = async (event) => {
    event.preventDefault();
    if (!file) {
      setError("Please upload a PDF file.");
      return;
    }
    if (!isPdf(file)) {
      setError("Only PDF files can be uploaded.");
      return;
    }

    const formData = new FormData();
    formData.append("document", file);
    setExtracting(true);
    setError("");
    setSuccess("");
    setRecord(null);

    try {
      const response = await axios.post(`${EXTRACT_API_BASE_URL}/extract`, formData);
      setRecord(response.data);
    } catch (err) {
      console.error("Record extraction failed:", err);
      setError(getErrorMessage(err, "The record could not be extracted."));
    } finally {
      setExtracting(false);
    }
  };

  const handleSave = async () => {
    if (!record) return;

    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const response = await axios.post(`${ENGAGEMENTS_API_BASE_URL}/engagements`, record, {
        headers: { "Content-Type": "application/json" },
      });
      setRecord(response.data);
      setSuccess("Record saved successfully.");
    } catch (err) {
      console.error("Record save failed:", err);
      setError(getErrorMessage(err, "The record could not be saved."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="upload-record">
      <h1>Upload Record</h1>
      <p className="upload-description">
        Upload a PDF to extract an engagement record, then review and save it.
      </p>
      {error && <p className="error" role="alert">{error}</p>}
      {success && <p className="success" role="status">{success}</p>}

      <form onSubmit={handleExtract}>
        <div className="form-group">
          <label htmlFor="file">Upload PDF:</label>
          <input type="file" id="file" accept="application/pdf,.pdf" onChange={handleFileChange} disabled={extracting || saving} />
        </div>
        <button type="submit" className="submit-button" disabled={extracting || saving}>
          {extracting ? "Extracting..." : "Extract Record"}
        </button>
        <button type="button" className="home-button" onClick={() => window.location.href = "/"}>Home</button>
      </form>

      {record && (
        <section className="record-preview" aria-live="polite">
          <div className="record-preview-header">
            <h2>Extracted Record</h2>
            <button type="button" className="save-button" onClick={handleSave} disabled={saving || extracting}>
              {saving ? "Saving..." : "Save Record"}
            </button>
          </div>
          <pre>{JSON.stringify(record, null, 2)}</pre>
        </section>
      )}
    </div>
  );
}

export default UploadRecord;
