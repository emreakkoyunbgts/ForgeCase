"""HTTP boundary models; the shared record and verdict contracts stay unchanged."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from common.drafts import Language, normalize_draft

SECTION_NAMES = {"context", "challenge", "approach", "technology", "outcomes"}
METADATA_NAMES = {"page", "id", "engagement_id", "engagement_ids", "source_ref"}
MAX_DRAFT_DEPTH = 32


def _walk(value):
    """Bound JSON nesting before the core serializes or examines the draft."""
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_DRAFT_DEPTH:
            raise ValueError("draft nesting exceeds 32 levels")
        yield item
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def validate_record_id(record_id: str) -> str:
    """A record ID must address one Vault path segment."""
    if not record_id.strip() or record_id in {".", ".."} or any(
        separator in record_id for separator in ("/", "\\")
    ):
        raise ValueError("record_id must identify one Vault record")
    return record_id


def _contains_text(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_contains_text(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_text(item) for key, item in value.items() if key not in METADATA_NAMES
        )
    return False


def validate_draft(draft: dict[str, Any]) -> dict[str, Any]:
    for _ in _walk(draft):
        pass
    # Both the single-source and Generator MCS contracts contain sections.
    sections = draft.get("sections")
    if not isinstance(sections, dict) or not any(
        _contains_text(sections.get(name)) for name in SECTION_NAMES
    ):
        raise ValueError("draft.sections must contain case-study text")
    return draft


def validate_draft_identity(draft: dict[str, Any], record_id: str) -> None:
    if "engagement_id" in draft and draft["engagement_id"] != record_id:
        raise ValueError("draft engagement_id must match record_id")
    if "engagement_ids" in draft and draft["engagement_ids"] != [record_id]:
        raise ValueError("draft engagement_ids must contain only record_id")
    # Generator MCS marks each section/title with its source ID in `page`.
    for content in (draft.get("sections", {}), draft.get("titles", [])):
        for item in _walk(content):
            if isinstance(item, dict) and "page" in item and item["page"] != record_id:
                raise ValueError("draft page source must match record_id")


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1)
    draft: dict[str, Any]
    language: Language = "en"

    _record_id = field_validator("record_id")(validate_record_id)
    _draft = field_validator("draft")(validate_draft)

    @model_validator(mode="after")
    def check_identity(self):
        validate_draft_identity(self.draft, self.record_id)
        self.draft = normalize_draft(self.draft, self.record_id, self.language)
        return self


class LegacyVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: dict[str, Any]
    mcs: dict[str, Any]

    _mcs = field_validator("mcs")(validate_draft)


class VerificationReport(BaseModel):
    engagement_id: str
    verdict: Literal["PASS", "BLOCK"]
    # Existing checks use value/why or detail/claim; retain both representations.
    problems: list[dict[str, Any]]
