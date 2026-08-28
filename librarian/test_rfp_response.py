import librarian.rfp_response as rfp_response

from librarian.rfp_response import (
    RFPResponseDependencyError,
    build_rfp_response,
    call_generator,
    call_verifier,
)


CORPUS = [
    {
        "id": "eng-01",
        "client": "Example Bank",
        "client_type": "Tier-1 GCC retail bank",
        "may_be_named": False,
        "domain": "payments",
        "region": "GCC",
        "challenge": "Legacy batch payments.",
        "solution": "Real-time payment architecture.",
        "technologies": ["Kafka"],
        "outcomes": ["Payment latency reduced 45%."],
    },
]


def evidenced_evaluation(**kwargs):
    return {
        "requirements": [
            {
                "requirement_id": "REQ-001",
                "text": "Support real-time payments.",
                "status": "EVIDENCED",
                "best_match": {
                    "engagement_id": "eng-01",
                    "retrieval_strategy": "hybrid",
                    "retrieval_score": 0.91,
                    "evidence_score": 0.82,
                    "why": "Strong payments evidence.",
                },
                "gap_reason": None,
            }
        ],
        "coverage": {
            "evidenced": 1,
            "gaps": 0,
            "total": 1,
            "ratio": 1.0,
        },
        "configuration": {
            "retrieval_strategy": "hybrid",
            "top_k": 3,
            "min_dense_score": 0.45,
        },
    }


def gap_evaluation(**kwargs):
    return {
        "requirements": [
            {
                "requirement_id": "REQ-001",
                "text": "Support quantum banking.",
                "status": "GAP",
                "best_match": None,
                "gap_reason": "No supporting evidence.",
            }
        ],
        "coverage": {
            "evidenced": 0,
            "gaps": 1,
            "total": 1,
            "ratio": 0.0,
        },
        "configuration": {},
    }


def generator_output():
    return {
        "engagement_ids": ["eng-01"],
        "titles": ["Real-time payments"],
        "sections": {
            "context": ["A Tier-1 GCC retail bank required modernization."],
            "challenge": ["Legacy batch payments limited processing."],
            "approach": ["BGTS implemented a real-time architecture."],
            "technology": ["Kafka was used for event processing."],
            "outcomes": ["Payment latency reduced 45%."],
        },
        "citations": [
            {
                "claim": "payment latency reduced 45%",
                "source_ref": "closeout.pdf#page=5",
            }
        ],
        "client_named": False,
    }


def test_evidenced_verified_requirement_is_supported():
    seen = {}

    def fake_generate(record, correlation_id):
        seen["generator_record"] = record
        seen["generator_correlation"] = correlation_id
        return generator_output()

    def fake_verify(record, mcs, correlation_id):
        seen["verifier_record"] = record
        seen["verifier_mcs"] = mcs
        seen["verifier_correlation"] = correlation_id

        return {
            "engagement_id": record["id"],
            "verdict": "PASS",
            "problems": [],
        }

    result = build_rfp_response(
        rfp_text="RFP",
        corpus=CORPUS,
        generate_proof=fake_generate,
        verify_proof=fake_verify,
        evaluate_fn=evidenced_evaluation,
    )

    item = result["requirements"][0]

    assert item["status"] == "SUPPORTED"
    assert item["engagement_id"] == "eng-01"
    assert "real-time architecture" in item["proof"]
    assert len(item["citations"]) == 1

    assert seen["generator_record"] == CORPUS[0]
    assert seen["verifier_record"] == CORPUS[0]
    assert seen["verifier_mcs"] == generator_output()
    assert (
        seen["generator_correlation"]
        == seen["verifier_correlation"]
    )

    assert result["summary"] == {
        "total_requirements": 1,
        "supported": 1,
        "gaps": 0,
    }


def test_gap_never_calls_generator_or_verifier():
    def should_not_generate(*args, **kwargs):
        raise AssertionError(
            "Generator must not run for a GAP."
        )

    def should_not_verify(*args, **kwargs):
        raise AssertionError(
            "Verifier must not run for a GAP."
        )

    result = build_rfp_response(
        rfp_text="RFP",
        corpus=CORPUS,
        generate_proof=should_not_generate,
        verify_proof=should_not_verify,
        evaluate_fn=gap_evaluation,
    )

    item = result["requirements"][0]

    assert item["status"] == "GAP"
    assert item["proof"] is None
    assert result["summary"]["gaps"] == 1


def test_verifier_block_turns_proof_into_gap():
    def fake_generate(record, correlation_id):
        return generator_output()

    def fake_verify(record, mcs, correlation_id):
        return {
            "engagement_id": record["id"],
            "verdict": "BLOCK",
            "problems": [
                {
                    "type": "unsupported_claim",
                    "value": "45%",
                    "why": "Claim not supported.",
                }
            ],
        }

    result = build_rfp_response(
        rfp_text="RFP",
        corpus=CORPUS,
        generate_proof=fake_generate,
        verify_proof=fake_verify,
        evaluate_fn=evidenced_evaluation,
    )

    item = result["requirements"][0]

    assert item["status"] == "GAP"
    assert item["proof"] is None
    assert item["citations"] == []
    assert item["verification"]["verdict"] == "BLOCK"


def test_uncited_generator_output_becomes_gap():
    def fake_generate(record, correlation_id):
        output = generator_output()
        output["citations"] = []
        return output

    def should_not_verify(*args, **kwargs):
        raise AssertionError(
            "Uncited proof must not reach Verifier."
        )

    result = build_rfp_response(
        rfp_text="RFP",
        corpus=CORPUS,
        generate_proof=fake_generate,
        verify_proof=should_not_verify,
        evaluate_fn=evidenced_evaluation,
    )

    item = result["requirements"][0]

    assert item["status"] == "GAP"
    assert item["proof"] is None


def test_generator_failure_degrades_to_gap():
    def unavailable_generator(record, correlation_id):
        raise RFPResponseDependencyError(
            "generator is down"
        )

    def should_not_verify(*args, **kwargs):
        raise AssertionError(
            "Verifier must not run after Generator failure."
        )

    result = build_rfp_response(
        rfp_text="RFP",
        corpus=CORPUS,
        generate_proof=unavailable_generator,
        verify_proof=should_not_verify,
        evaluate_fn=evidenced_evaluation,
    )

    item = result["requirements"][0]

    assert item["status"] == "GAP"
    assert "Generator unavailable" in item["gap_reason"]


def test_call_generator_uses_generator_contract(monkeypatch):
    seen = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return generator_output()

    def fake_post(url, json, headers, timeout):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(
        rfp_response.requests,
        "post",
        fake_post,
    )

    result = call_generator(
        CORPUS[0],
        "corr-123",
    )

    assert seen["url"].endswith(
        "/generator/mcs/eng"
    )
    assert seen["json"] == CORPUS[0]
    assert (
        seen["headers"]["X-Correlation-ID"]
        == "corr-123"
    )
    assert result["engagement_ids"] == ["eng-01"]


def test_call_verifier_uses_verifier_contract(monkeypatch):
    seen = {}
    mcs = generator_output()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "engagement_id": "eng-01",
                "verdict": "PASS",
                "problems": [],
            }

    def fake_post(url, json, headers, timeout):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(
        rfp_response.requests,
        "post",
        fake_post,
    )

    result = call_verifier(
        CORPUS[0],
        mcs,
        "corr-456",
    )

    assert seen["url"].endswith(
        "/verify/eng-01"
    )
    assert seen["json"] == {
        "record": CORPUS[0],
        "mcs": mcs,
    }
    assert (
        seen["headers"]["X-Correlation-ID"]
        == "corr-456"
    )
    assert result["verdict"] == "PASS"