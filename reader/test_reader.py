"""Tests for the Reader. Write more — especially failure cases."""
from reader.reader import extract_record


def test_returns_a_record_with_required_fields():
    """A record must always have the contract's required fields."""
    record = extract_record("some text", "eng-01_closeout.pdf")
    for field in ["id", "client", "client_type", "may_be_named", "outcomes"]:
        assert field in record, f"record is missing '{field}'"


def test_every_outcome_has_a_source_ref():
    """THE CORE RULE: every fact must say where it came from."""
    record = extract_record("some text", "eng-01_closeout.pdf")
    for outcome in record["outcomes"]:
        assert outcome.get("source_ref"), \
            "every outcome MUST have a source_ref — see the spec, section 3.2"


# TODO(Çağrı): add a test that eng-12 produces outcome_missing = True
# TODO(Çağrı): add a test that a corrupt PDF exits with code 2, not a traceback
