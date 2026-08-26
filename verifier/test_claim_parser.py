import pytest
import json
from pathlib import Path
from verifier.claim_parser import ClaimParser

@pytest.fixture
def parser():
    return ClaimParser()

# 1. Sentence Splitting Test
def test_sentence_splitting(parser):
    text = "The shadow migration as completed in 11 months for Gulf Union Bank. Payment latency was reduced by 45%."
    sentences = parser.split_into_sentences(text)
    assert len(sentences) == 2
    assert "11 months" in sentences[0]
    assert "45%" in sentences[1]

# 2. Metric Claim Extraction Test
def text_extract_metric_claims(parser):
    sentence = "Payment latency was reduced by 45%."
    claims = parser.extract_atomic_claims(sentence)

    assert len(claims) > 0
    metric_claims = [c for c in claims if c["type"] == "metric_claim"]
    assert len(metric_claims) == 1
    assert metric_claims[0]["target_value"] == "45%"

# 3. Customer Claim Extraction Test
def test_client_claim_extraction(parser):
    sentence = "The solution was deployed for a Tier-1 GCC retail bank."
    claims = parser.extract_atomic_claims(sentence)

    client_claims = [c for c in claims if c["type"] == "client_claim"]
    assert len(client_claims) == 1

# 4. Reading Clean JSON Test
def test_parse_clean_json(parser):
    sample_file = Path("caseforge-testdata/case_studies/eng-01_clean.json")
    if not sample_file.exists():
        sample_file = Path("case_studies/eng-01_clean.json")

    if sample_file.exists():
        with open(sample_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        claims = parser.parse_case_study(data)
        assert isinstance(claims, list)
        assert len(claims) > 0

# 5. Edge-Case / Crash Prevention Tests
def test_edge_cases_and_crash_prevention(parser):
    # Should not crash when entered None, number, epsilon or mistype
    assert parser.split_into_sentences(None) == []
    assert parser.extract_atomic_claims(12345) == []
    assert parser.parse_case_study({}) == []
    assert parser.parse_case_study("invalid_json_string") == [] 

# The 6th function(test_error_case_control(parser)) is a test function for error cases
# If you want it to catch the errors you can simply remove the DOC strings and run the test
"""
# 6. An Extra Error Test
def test_error_case_control(parser):
    text = "The shadow migration was completed in 11 months for Gulf Union Bank."
    sentences = parser.split_into_sentences(text)
    # Giving 99 as input on purpose to test the error catching mechanism
    assert len(sentences) == 99
"""