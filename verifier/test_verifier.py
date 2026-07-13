"""
Tests for the Verifier.

These two tests ARE the product. If they pass, CaseForge can be trusted.
"""
import json

from common.contract import load_seed
from verifier.verifier import verify


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_clean_case_study_passes():
    """A properly grounded case study must produce NO problems."""
    case_study = load("caseforge-testdata/case_studies/eng-01_clean.json")
    record = load_seed("eng-01")

    report = verify(case_study, record)

    assert report["verdict"] == "PASS", \
        f"false alarm! flagged: {report['problems']}"


def test_poisoned_case_study_is_blocked():
    """
    THE TEST THAT MATTERS.

    The poisoned file contains 5 invented facts:
      - a fake 42% cost saving
      - a fake 300% satisfaction increase
      - a wrong duration (3 months; it was 11)
      - a wrong year (2019)
      - the client NAMED without consent
    """
    case_study = load("caseforge-testdata/case_studies/eng-01_POISONED.json")
    record = load_seed("eng-01")

    report = verify(case_study, record)

    assert report["verdict"] == "BLOCK", "an invented fact got through!"

    flagged = {p["value"] for p in report["problems"]}
    assert "42%" in flagged, "missed the invented 42% cost saving"
    assert "300%" in flagged, "missed the invented 300% figure"
    assert "Gulf Union Bank" in flagged, "missed the client named without consent"

    # ...and it must NOT flag the figures that are genuinely in the source
    assert "45%" not in flagged, "false alarm: 45% IS in the source"


# TODO(Ömer): the poisoned file also has a wrong "3 months" and "2019".
#   The naive number check may miss them. Make it catch those too.
