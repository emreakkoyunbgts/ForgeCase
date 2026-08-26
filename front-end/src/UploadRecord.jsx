import React, { useState } from 'react';
import './UploadRecord.css';

function UploadRecord() {
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!file) {
      setError("Please upload a file.");
      return;
    }
    setError("");
    console.log("File uploaded:", file);
    // Add logic to handle file upload
  };

  return (
    <div className="upload-record">
      <h1>Upload Record</h1>
      {error && <p className="error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="file">Upload PDF:</label>
          <input
            type="file"
            id="file"
            accept="application/pdf"
            onChange={handleFileChange}
          />
        </div>
        <button type="submit" className="submit-button">Submit</button>
        <button type="button" className="home-button" onClick={() => window.location.href = '/'}>Home</button>
      </form>
    </div>
  );
}

export default UploadRecord;
