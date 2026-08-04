import pytest
from verifier.entailment_checker import EntailmentChecker
import random

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

def test_check_paraphrased_claims_detects_unsupported_boasts():
    """
    Test: It should raise an 'unsupported_qualitative_claim' error when the text contains exaggerated
     claims—such as 'huge success' or 'costs fell dramatically'—while the source data (ground truth)
     contains no confirmation or metrics regarding them.
    """
    checker = EntailmentChecker()

    draft_claim = "The project was a huge success and costs fell dramatically."
    ground_truth = {
        "status": "completed",
        "supports_qualitative_claims": False
    }

    problems = checker.check_paraphrased_claims(draft_claim, ground_truth)

    # Must catch at least 2 violations ('huge success' and 'dramatically')
    assert len(problems) == 2
    assert problems[0]["type"] == "unsupported_qualitative_claim"
    assert "huge success" in problems[0]["detail"]
    assert "dramatically" in problems[1]["detail"]

def test_check_paraphrased_claims_passess_when_supported():
    """
    Test: The test must pass (PASS) when the source data has 'supports_qualitative_claims: True'
     or when no exaggerated words are present.
    """
    checker = EntailmentChecker()

    draft_claim = "The project was completed on schedule."
    ground_truth = {
        "status": "completed",
        "supports_qulitative_claims": False
    }

    problems = checker.check_paraphrased_claims(draft_claim, ground_truth)

    # No problems should be catched
    assert len(problems) == 0

def randomize_case(text: str) -> str:
    """
    Randomly converts each character in the text to uppercase or lowercase (with a 50% chance).
    E.g.: 'huge success' -> 'hUGesUcCEss' or 'HUge SUCCess'
    """
    return "".join(
        char.upper() if random.choice([True, False]) else char.lower() for char in text
    )

def test_check_paraphrased_claims_with_true_random_casing():
    """
    Edge Case: Even if the letters are distributed in a completely unpredictable and
     random manner—such as 2 uppercase, 3 lowercase, 1 uppercase—the system must capture them all.
    """
    checker = EntailmentChecker()
    ground_truth = {"status": "completed"} # With missing key edge case

    base_claim = "The project was a huge success and costs fell dramatically."

    # Test on different completely random variation

    for _ in range(5):
        randomized_claim = randomize_case(base_claim)

        problems = checker.check_paraphrased_claims(randomized_claim, ground_truth)

        # No matter how many times we run through it, a "huge success" and a "dramatic" effect must be achieved
        assert len(problems) == 2, f"Unsuccessful in randomized text: {randomized_claim}"
        assert problems[0]["type"] == "unsupported_qualitative_claim"
