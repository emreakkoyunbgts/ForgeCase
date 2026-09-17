"""
PUBLISHER SERVICE — exposes publisher.py over HTTP.

    python -m publisher.service

POST /publish   {"record_id": "eng-01"}  -> branded document path
GET  /health    -> {"status": "ok"}
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, request, jsonify

from common.contract import load_corpus
from common.services import VAULT_URL, call_service
from publisher.publisher import render_docx, TEMPLATE

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/publish", methods=["POST"])
def publish():
    data = request.get_json(silent=True) or {}
    record_id = data.get("record_id")
    if not record_id:
        return jsonify({"error": "record_id is required"}), 400

    try:
        response = call_service("GET", f"{VAULT_URL}/records/{record_id}")
        record = response.json()
    except Exception:
        corpus = load_corpus()
        record = next((r for r in corpus if r["id"] == record_id), None)
        if record is None:
            return jsonify({"error": f"no such record: {record_id}"}), 404

    case_study = {
        "title": record.get("id", "[MISSING]"),
        "sections": {
            "context": record.get("client", "[MISSING]") if record.get("may_be_named") else "[REDACTED]",
            "challenge": record.get("challenge", "[MISSING]"),
            "approach": record.get("solution", "[MISSING]"),
            "technology": ", ".join(record.get("technologies", [])),
            "outcomes": str(record.get("outcomes", "[MISSING]")),
        },
    }

    out_path = f"out/{record_id}.docx"
    written = render_docx(case_study, TEMPLATE, out_path)

    return jsonify({"path": str(written)})


if __name__ == "__main__":
    app.run(port=8005)