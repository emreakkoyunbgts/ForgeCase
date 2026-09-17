"""Single-source draft contract shared by HTTP clients and renderers.

Only the text returned by ``rendered_spans`` may be rendered as case-study
content. Normalization changes representation, never the submitted prose.
"""

import hashlib
import json
from typing import Literal

Language = Literal["en", "de", "tr"]
LANGUAGES = {"en", "de", "tr"}
SECTION_FIELDS = {
    "context": "region", "challenge": "challenge", "approach": "approach",
    "technology": "technologies", "outcomes": "outcomes",
}
MAX_DRAFT_CHARACTERS = 24000


def validate_record_id(record_id):
    if (not isinstance(record_id, str) or not record_id.strip()
            or record_id in {".", ".."} or len(record_id) > 200
            or any(c in record_id for c in "/\\")
            or any(ord(c) < 32 for c in record_id)):
        raise ValueError("record_id must identify one Vault record")
    return record_id


def _text(value):
    if not isinstance(value, str):
        raise ValueError("draft prose must be text")
    return value


def normalize_draft(draft, record_id, language="en"):
    """Accept flat section strings or MCS lists; return canonical single-source MCS."""
    validate_record_id(record_id)
    if language not in LANGUAGES:
        raise ValueError("language must be en, de or tr")
    if not isinstance(draft, dict):
        raise ValueError("draft must be an object")
    allowed = {"engagement_id", "engagement_ids", "title", "titles", "sections",
               "citations", "client_named", "language"}
    if set(draft) - allowed:
        raise ValueError("draft contains unsupported fields")
    if "engagement_id" in draft and draft["engagement_id"] != record_id:
        raise ValueError("draft engagement_id must match record_id")
    if "engagement_ids" in draft and draft["engagement_ids"] != [record_id]:
        raise ValueError("draft engagement_ids must contain only record_id")
    if draft.get("language", language) != language:
        raise ValueError("draft language must match request language")
    if "client_named" in draft and not isinstance(draft["client_named"], bool):
        raise ValueError("draft client_named must be boolean")
    if "title" in draft and "titles" in draft:
        raise ValueError("draft must use title or titles, not both")

    def entries(value, field):
        if isinstance(value, str):
            return [{field: value, "page": record_id}]
        if not isinstance(value, list):
            raise ValueError("draft sections and titles must be text or lists")
        result = []
        for item in value:
            if not isinstance(item, dict) or set(item) - {field, "page"} or field not in item:
                raise ValueError("draft contains an invalid text entry")
            if item.get("page", record_id) != record_id:
                raise ValueError("draft page source must match record_id")
            result.append({field: _text(item[field]), "page": record_id})
        return result

    sections = draft.get("sections")
    if not isinstance(sections, dict) or set(sections) - set(SECTION_FIELDS):
        raise ValueError("draft.sections must contain standard case-study sections")
    normalized_sections = {
        name: entries(sections[name], field) if name in sections else []
        for name, field in SECTION_FIELDS.items()
    }
    if not any(item[field].strip() for name, field in SECTION_FIELDS.items()
               for item in normalized_sections[name]):
        raise ValueError("draft.sections must contain case-study text")
    citations = draft.get("citations", [])
    if not isinstance(citations, list):
        raise ValueError("draft citations must be a list")
    normalized_citations = []
    for citation in citations:
        if (not isinstance(citation, dict)
                or set(citation) - {"claim", "source_ref", "page_ref"}
                or not {"claim", "source_ref"} <= set(citation)):
            raise ValueError("draft contains an invalid citation")
        if citation.get("page_ref", record_id) != record_id:
            raise ValueError("citation page_ref must match record_id")
        normalized_citations.append({
            "claim": _text(citation["claim"]),
            "source_ref": _text(citation["source_ref"]), "page_ref": record_id,
        })
    result = {
        "engagement_ids": [record_id],
        "titles": entries(draft.get("titles", draft.get("title", [])), "title"),
        "sections": normalized_sections, "citations": normalized_citations,
        "client_named": draft.get("client_named", False), "language": language,
    }
    if len(json.dumps(result, ensure_ascii=False)) > MAX_DRAFT_CHARACTERS:
        raise ValueError("draft exceeds the 24000-character limit")
    return result


def rendered_spans(draft):
    """Return exact title, section and citation prose with stable JSON pointers."""
    spans = []
    for i, entry in enumerate(draft["titles"]):
        spans.append({"id": f"/titles/{i}/title", "text": entry["title"]})
    for section, field in SECTION_FIELDS.items():
        for i, entry in enumerate(draft["sections"][section]):
            spans.append({"id": f"/sections/{section}/{i}/{field}", "text": entry[field]})
    for i, citation in enumerate(draft["citations"]):
        spans.append({"id": f"/citations/{i}/claim", "text": citation["claim"]})
    return [span for span in spans if span["text"].strip()]


def draft_hash(draft):
    encoded = json.dumps(draft, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def display_case_study(draft, record_id, language="en"):
    canonical = normalize_draft(draft, record_id, language)
    return {
        "engagement_id": record_id,
        "title": "\n".join(item["title"] for item in canonical["titles"]),
        "sections": {name: "\n".join(item[field] for item in canonical["sections"][name])
                     for name, field in SECTION_FIELDS.items()},
        "citations": canonical["citations"], "client_named": canonical["client_named"],
        "language": language,
    }
