"""
CF-60: Adversarial Test Suite for L5 Verification DSL
Tests edge cases, adversarial inputs, and pattern bypass attempts.
"""

import pytest
from verifier.dsl import RuleEngineDSL
from verifier.entailment_checker import EntailmentChecker

@pytest.fixture
def checker():
    return EntailmentChecker()

@pytest.fixture
def dsl():
    return RuleEngineDSL()

def test_dsl_rule_loading(dsl):
    # Verify that DSL rules load dynamically and provide active patterns.
    patterns = dsl.get_qualitative_patterns()
    assert len(patterns) >= 10
    assert dsl.is_rule_active("qualitative_claims")

def test_adversarial_case_insensivity_and_whitespace(checker):
    # Adversarial Test: Mixed casing and multi-space bypass attempts.
    text = "The product achieved a HuGe    SuCcEsS in performance."
    ground_truth = {"supports_qualitative_claims": False}

    problems = checker.check_paraphrased_claims(text, ground_truth)
    assert len(problems) > 0
    assert problems[0]["type"] == "unsupported_qualitative_claim"

def test_adversarial_metric_hallucination(checker):
    # Adversarial Test: Attempt to pass unverified numbers via trailing text.
    extracted_claims = ["Revenue grew by 99%"]
    record_outcomes = [{"metric": "Revebue grew by 20%"}]

    is_valid = checker.verify_metrics(extracted_claims, record_outcomes)
    assert is_valid is False

def test_adversarial_client_privacy_obfuscation(checker):
    # Adversarial Test: Privacy breach with extra spacing or punctuation.
    draft_text = "Project executed for Acme-Corp internal systems."
    record_client = "Acme-Corp"

    is_valid = checker.verify_client_naming(draft_text, record_client, may_be_named=False)
    assert is_valid is False
