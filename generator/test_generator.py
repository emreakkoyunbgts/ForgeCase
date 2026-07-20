"""Tests for the Generator. The second one is the important one."""
from common.contract import load_seed, load_corpus
from generator.generator import generate, get_five_sections_with_llm


def test_produces_all_five_sections():
    case_study = generate(load_seed("eng-01"))
    for section in ["context", "challenge", "approach", "technology", "outcomes"]:
        assert section in case_study["sections"]


def test_does_not_invent_an_outcome_when_there_is_none():
    """
    THE MOST IMPORTANT TEST IN THIS PROJECT.

    eng-12 has NO measurable outcome. The generator must say so — it must
    not quietly produce a plausible-sounding number.
    """
    eng12 = next(r for r in load_corpus() if r["id"] == "eng-12")
    case_study = generate(eng12)
    outcomes = case_study["sections"]["outcomes"]
    print("eng-12 case_study: "+str(case_study))
    assert "MISSING" in outcomes, \
        "eng-12 has no outcomes — the output MUST say so, not invent one"
    assert not any(ch.isdigit() for ch in outcomes), \
        f"a number appeared from nowhere: {outcomes!r}"


def test_client_is_anonymised_by_default():
    """eng-01 may NOT be named. The real name must never appear."""
    record = load_seed("eng-01")
    case_study = generate(record)
    blob = str(case_study)
    assert record["client"] not in blob, \
        "the real client name leaked into the output — see spec section 7"


# TODO(Taha): test that the prompt-injection document does not change behaviour

def test_get_five_sections_with_llm():
    record = load_seed("eng-01")

    case_study = get_five_sections_with_llm(record)

    assert isinstance(case_study, dict)

    expected_sections = [
        "context",
        "challenge",
        "approach",
        "technology",
        "outcomes",
    ]

    print("llm s case study : "+str(case_study))

    for section in expected_sections:
        assert section in case_study
        assert isinstance(case_study[section], str)
        assert case_study[section].strip() != ""


def test_generate_casestudy_from_seed_eng07():
    case_study = generate(load_seed("eng-07"))
    print("case study from eng-07: "+str(case_study))
    for section in ["context", "challenge", "approach", "technology", "outcomes"]:
        assert section in case_study["sections"]

def test_generate_casestudy_from_seed_eng08():
    case_study = generate(load_seed("eng-08"))
    print("case study from eng-08: "+str(case_study))
    for section in ["context", "challenge", "approach", "technology", "outcomes"]:
        assert section in case_study["sections"]

def test_generate_casestudy_from_seed_eng09():
    case_study = generate(load_seed("eng-09"))
    print("case study from eng-09: "+str(case_study))
    for section in ["context", "challenge", "approach", "technology", "outcomes"]:
        assert section in case_study["sections"]

def test_generate_casestudy_from_seed_eng10():
    case_study = generate(load_seed("eng-10"))
    print("case study from eng-10: "+str(case_study))
    for section in ["context", "challenge", "approach", "technology", "outcomes"]:
        assert section in case_study["sections"]