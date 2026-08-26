import React, { useState } from 'react';
import './AddRecord.css';

const REQUIRED_FIELDS = [
  "id", "client", "client_type", "may_be_named", "domain", "region",
  "challenge", "solution", "technologies", "outcomes",
];

const VALID_REGIONS = ["UK", "DE", "NL", "TR", "GCC"];

function AddRecord() {
  const [formData, setFormData] = useState({ may_be_named: "true" });
  const [error, setError] = useState("");

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const missingFields = REQUIRED_FIELDS.filter(field => !formData[field]);
    if (missingFields.length > 0) {
      setError(`Missing fields: ${missingFields.join(", ")}`);
      return;
    }
    if (!VALID_REGIONS.includes(formData.region)) {
      setError("Invalid region selected.");
      return;
    }
    setError("");
    console.log("Record added:", formData);
  };

  return (
    <div className="add-record-container">
      <div className="add-record-header">
        <h1>Add Record</h1>
        <a href="/records" className="back-button">Back to Records</a>
      </div>

      <form className="add-record-form" onSubmit={handleSubmit}>
        {REQUIRED_FIELDS.map((field) => (
          <div key={field}>
            <label htmlFor={field}>{field.replace(/_/g, ' ')}</label>
            {field === "region" ? (
              <select
                id={field}
                name={field}
                value={formData[field] || ""}
                onChange={handleChange}
              >
                <option value="">Select Region</option>
                {VALID_REGIONS.map((region) => (
                  <option key={region} value={region}>
                    {region}
                  </option>
                ))}
              </select>
            ) : field === "may_be_named" ? (
              <select
                id={field}
                name={field}
                value={formData[field] || ""}
                onChange={handleChange}
              >
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            ) : field === "outcomes" ? (
              <textarea
                id={field}
                name={field}
                value={formData[field] || ""}
                onChange={handleChange}
              />
            ) : (
              <input
                id={field}
                name={field}
                value={formData[field] || ""}
                onChange={handleChange}
              />
            )}
          </div>
        ))}

        <button type="submit">Submit</button>
      </form>
    </div>
  );
}

export default AddRecord;