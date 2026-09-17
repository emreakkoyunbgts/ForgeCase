"""Grounded extraction for the supported text-layer closeout PDF format."""

import os
import re

from common.contract import VALID_REGIONS
from reader import layout
from reader.reader import ExtractionError


def _text(value):
    return " ".join(str(value).split())


def build_record(analysis, source_name):
    """Build a record only from explicit labelled fields and numbered sections."""
    if not isinstance(analysis, dict) or not analysis.get("pages"):
        raise ExtractionError("structured document evidence is required")
    fields = {}
    sections = {}
    for page in analysis["pages"]:
        for key, evidence in page.get("fields", {}).items():
            if evidence.get('conflicts'):
                raise ExtractionError(f"conflicting document field: {key}")
            value = evidence["value"]
            if key in {'team_size', 'duration_months'}:
                suffix = r'(?:months?|monate|monaten|ay)?' if key == 'duration_months' else r'(?:people|persons?|members?)?'
                if not re.fullmatch(r'\d+\s*' + suffix, str(evidence.get('raw', value)).strip(), re.I):
                    raise ExtractionError(f"ambiguous document field: {key}")
            if key in fields and fields[key] != value:
                raise ExtractionError(f"conflicting document field: {key}")
            fields[key] = value
        for section in page.get("sections", []):
            heading = re.sub(r"^(the|our)\s+", "", section["heading"].strip().lower())
            heading = {"solution": "approach", "technologies": "technology"}.get(heading, heading)
            if heading in {"challenge", "approach", "technology", "outcomes"}:
                sections.setdefault(heading, []).append((page["page"], section["text"]))

    required = ("id", "client", "client_type", "domain", "region")
    missing = [key for key in required if not isinstance(fields.get(key), str) or not fields[key].strip()]
    missing += [key for key in ("challenge", "approach") if not any(text.strip() for _, text in sections.get(key, []))]
    if missing:
        raise ExtractionError("missing required document fields: " + ", ".join(missing))
    record_id = fields["id"].strip()
    if record_id in {".", ".."} or any(char in record_id for char in "/\\") or any(ord(char) < 32 for char in record_id):
        raise ExtractionError("engagement ID must identify one Vault record")
    region = fields["region"].strip()
    if region not in VALID_REGIONS:
        raise ExtractionError("region must be one of UK, DE, NL, TR, GCC")

    source = str(source_name).replace("\\", "/").rsplit("/", 1)[-1]
    outcomes = []
    for page, text in sections.get("outcomes", []):
        # Absence of measured outcomes is recorded honestly, never filled in.
        if not text.strip() or re.search(r"\bno (?:measurable |quantified )?outcomes?\b|\b(?:outcomes?|results?) (?:were |are )?not (?:recorded|available)\b", text, re.I):
            continue
        bullets = re.split(r"(?m)^\s*[-•]\s+", text)
        for bullet in bullets:
            metric = _text(bullet)
            if metric:
                outcomes.append({"metric": metric, "source_ref": f"{source}#page={page}"})
    technology = " ".join(text for _, text in sections.get("technology", []))
    record = {
        "id": record_id,
        "client": fields["client"].strip(),
        "client_type": fields["client_type"].strip(),
        "may_be_named": False,
        "domain": fields["domain"].strip(),
        "region": region,
        "challenge": _text(" ".join(text for _, text in sections["challenge"])),
        "solution": _text(" ".join(text for _, text in sections["approach"])),
        "technologies": list(dict.fromkeys(_text(value) for value in re.split(r"[,;\n]", technology) if value.strip())),
        "outcomes": outcomes,
        "outcome_missing": not bool(outcomes),
    }
    for key in ("team_size", "duration_months"):
        if isinstance(fields.get(key), int) and not isinstance(fields[key], bool):
            record[key] = fields[key]
    return record


def extract_document(pdf_path, source_name):
    """Read a structural closeout PDF; this production path never invokes OCR."""
    if not os.path.exists(pdf_path):
        raise ExtractionError(f"no such file: {source_name}")
    if os.path.getsize(pdf_path) == 0:
        raise ExtractionError(f"{source_name}: file is empty")
    try:
        analysis = layout.analyse(pdf_path)
    except Exception as exc:
        raise ExtractionError(f"could not read {source_name}: invalid PDF") from exc
    if not analysis.get("text", "").strip():
        raise ExtractionError(f"{source_name}: a text-layer closeout PDF is required; scans are unsupported")
    try:
        return build_record(analysis, source_name)
    except ExtractionError as exc:
        raise ExtractionError(f"{source_name}: {exc}") from exc
