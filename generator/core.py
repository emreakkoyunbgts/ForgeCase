"""Deterministic, in-memory MCS generation; no PDF, LLM or service imports."""

from common.contract import client_label
from common.drafts import normalize_draft


def generate_mcs(record):
    record_id = record["id"]
    label = client_label(record)
    outcomes = record.get("outcomes", [])
    def entry(field, text):
        return [{field: text, "page": record_id}]
    draft = {
        "engagement_ids": [record_id],
        "titles": entry("title", f"{record.get('domain') or '[MISSING: domain]'} for {label}"),
        "sections": {
            "context": entry("region", f"{label} in {record.get('region') or '[MISSING: region]'}."),
            "challenge": entry("challenge", record.get("challenge") or "[MISSING: challenge description]"),
            "approach": entry("approach", record.get("solution") or "[MISSING: solution description]"),
            "technology": entry("technologies", ", ".join(record.get("technologies", [])) or "[MISSING: technologies used]"),
            "outcomes": entry("outcomes", "; ".join(o["metric"] for o in outcomes)
                              or "[MISSING: no measurable outcome was recorded for this engagement]"),
        },
        "citations": [{"claim": o["metric"], "source_ref": o["source_ref"], "page_ref": record_id}
                      for o in outcomes],
        "client_named": record.get("may_be_named") is True,
    }
    return normalize_draft(draft, record_id, "en")
