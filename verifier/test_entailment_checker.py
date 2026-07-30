import pytest
from verifier.entailment_checker import EntailmentChecker

def test_verify_client_naming_violation():
    checker = EntailmentChecker()
    draft = "This project was built for Gulf Union Bank in GCC."
    client = "Gulf Union Bank"
    # If there is no privacy permission (False) and there is a name should catch the violation (False)
    assert checker.verify_client_naming(draft, client, False) is False

def test_verify_client_naming_allowed():
    checker = EntailmentChecker()
    draft = "This project was built for Gulf Union Bank in GCC."
    client = "Gulf Union Bank"
    # If there is a privacy permission (True) no problem (True)
    assert checker.verify_client_naming(draft, client, True) is True

def test_verify_metrics_success():
    checker = EntailmentChecker()
    extracted_claims = ["payment latency reduced 45%"]
    record_outcomes = [{"metric": "payment latency reduced 45%", "source_ref": "closeout.pdf#page=5"}]
    # Metric is in the record as it is, should return True
    assert checker.verify_metrics(extracted_claims, record_outcomes) is True

def test_verify_metrics_paraphrased_success():
    checker = EntailmentChecker()
    # A different order but '45%' is true!
    extracted_claims = ["latency was reduced by 45%"]
    record_outcomes = [{"metric": "payment latency reduced 45%", "source_ref": "closeout.pdf#page=5"}]
    assert checker.verify_metrics(extracted_claims, record_outcomes) is True

def test_verify_metrics_mismatch():
    checker = EntailmentChecker()
    extracted_claims = ["payment latency reduced 99%"] # Fake/False %99 metric
    record_outcomes = [{"metric": "payment latency reduced 45%", "source_ref": "closeout.pdf#page=5"}]
    # Metric is not in the record, should return False!
    assert checker.verify_metrics(extracted_claims, record_outcomes) is False

def test_verify_metrics_edge_case_empty_and_none():
    checker = EntailmentChecker()
    assert checker.verify_metrics([], []) is True
    assert checker.verify_metrics(None, None) is True

def test_verify_client_naming_edge_case_none():
    checker = EntailmentChecker()
    assert checker.verify_client_naming(None, "Gulf Bank", False) is True
    assert checker.verify_client_naming("Some draft text", None, False) is True

def test_verify_metrics_with_punctuation():
    checker = EntailmentChecker()
    extracted_claims = ["Latency reduced by 45%."]
    record_outcomes = [{"metric": "45% reduction"}]
    assert checker.verify_metrics(extracted_claims, record_outcomes) is True
