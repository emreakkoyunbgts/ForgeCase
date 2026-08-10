"""Tests for the Generator. The second one is the important one."""
import asyncio

import pytest

from common.contract import load_seed, load_corpus
from generator.generator import generate, get_five_sections_with_llm, generate_multi_source, generate_single_stream, \
    get_llm_punchy, get_llm_concise, generate_two_source, chech_llm_output_with_source
import re , json
import time

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

'''
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
        #assert isinstance(case_study[section], str)
        #assert case_study[section].strip() != ""

'''

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

def test_generate_eng12():
    case_study = generate(load_seed("eng-12"))
    print("case study from eng-12: "+str(case_study))
    for section in ["context", "challenge", "approach", "technology", "outcomes"]:
        assert section in case_study["sections"]

def test_generate_eng13():
    case_study = generate(load_seed("eng-13"))
    print("case study from eng-13: "+str(case_study))
    for section in ["context", "challenge", "approach", "technology", "outcomes"]:
        assert section in case_study["sections"]

        #HALLUCINATION TEST:

def ungrounded_numbers (output_text, record):
    """Any number in the output that is NOT in the source was invented."""
    in_output=set(re.findall(r"\d+(?:\.\d+)?%?", output_text))
    in_source=set(re.findall(r"\d+(?:\.\d+)?%?", json.dumps(record)))
    invented=in_output-in_source
    return invented

def test_no_hallucinated_numbers():
    """Any number in the output that is NOT in the source was invented."""
    record = load_seed("eng-01")
    output = get_five_sections_with_llm(record)
    output_text= json.dumps(output, ensure_ascii=False)
    invented = ungrounded_numbers(output_text, record)
    print("Invented numbers: "+str(invented))
    assert invented==set() , f"Invented numbers: {invented}"
def test_no_hallucinated_numbers_eng12():
    """Any number in the output that is NOT in the source was invented."""
    record = load_seed("eng-12")
    output = get_five_sections_with_llm(record)
    output_text= json.dumps(output, ensure_ascii=False)
    invented = ungrounded_numbers(output_text, record)
    print("Invented numbers: "+str(invented))
    assert invented==set() , f"Invented numbers: {invented}"




def test_generate_one_stream():
    record1 = load_seed("eng-01")
    record2 = load_seed("eng-02")

    start_time = time.perf_counter()

    llm_out = generate_single_stream([record1, record2])

    elapsed_time = time.perf_counter() - start_time

    print(f"Execution time: {elapsed_time:.2f} seconds")
    print("llm_out:", llm_out)


    invented=ungrounded_numbers(json.dumps(llm_out, ensure_ascii=False), [record1, record2])
    assert invented==set() , f"Invented numbers: {invented}"

    # Response time check
    assert elapsed_time < 30, (
        f"LLM generation took too long: {elapsed_time:.2f} seconds"
    )

def test_multi_source_generate():
    record1=load_seed("eng-01")
    record2=load_seed("eng-02")
    tcs=generate_two_source(record1, record2)
    for section in ["context", "challenge", "approach", "technology", "outcomes"]:
        assert section in tcs["sections"]


def test_multi_source_generate_list():
    records=[load_seed("eng-01"), load_seed("eng-02"), load_seed("eng-03")]
    tcs=generate_multi_source(records)
    for section in ["context", "challenge", "approach", "technology", "outcomes"]:
        assert section in tcs["sections"]

def test_multi_source_generate_list_with_eng12():
    records=[load_seed("eng-01"), load_seed("eng-02"), load_seed("eng-12")]
    tcs=generate_multi_source(records)
    for section in ["context", "challenge", "approach", "technology", "outcomes"]:
        assert section in tcs["sections"]


def test_multi_source_generate_list_with_eng13():
    records=[load_seed("eng-01"), load_seed("eng-02"), load_seed("eng-13")]
    tcs=generate_multi_source(records)
    for section in ["context", "challenge", "approach", "technology", "outcomes"]:
        assert section in tcs["sections"]


def test_punchy_llm_output():

    start_time = time.perf_counter()
    mcs=generate_multi_source([load_seed("eng-03"), load_seed("eng-12")])
    llm_punchy=get_llm_punchy(mcs)

    invented=ungrounded_numbers(json.dumps(llm_punchy, ensure_ascii=False),
                                [load_seed("eng-03"), load_seed("eng-12")])



    end_time= time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time:.2f} seconds")
    print("llm_punchy:", llm_punchy)
    assert elapsed_time < 30, (
        f"LLM generation took too long: {elapsed_time:.2f} seconds"
    )
    assert invented==set() , f"Invented numbers: {invented}"

def test_concise_llm_output():
    start_time = time.perf_counter()
    mcs = generate_multi_source([load_seed("eng-03"), load_seed("eng-12")])
    llm_concise = get_llm_concise(mcs)

    invented = ungrounded_numbers(json.dumps(llm_concise, ensure_ascii=False),
                                  [load_seed("eng-03"), load_seed("eng-12")])

    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time:.2f} seconds")
    print("llm_punchy:", llm_concise)
    assert elapsed_time < 30, (
        f"LLM generation took too long: {elapsed_time:.2f} seconds"
    )
    assert invented == set(), f"Invented numbers: {invented}"


def test_generate_eng2():
    case_study = generate_multi_source([load_seed("eng-02")])
    print("case study from eng-02: "+str(case_study))

    get_five_sections_with_llm(case_study)

    for section in ["context", "challenge", "approach", "technology", "outcomes"]:
        assert section in case_study["sections"]


def test_check_mcs2():
    mcs={'engagement_ids': ['eng-02'], 'titles': [{'title': 'regulatory reporting for Nordbank Deutschland', 'page': 'eng-02'}], 'sections': {'context': [{'region': 'Nordbank Deutschland in DE.', 'page': 'eng-02'}], 'challenge': [{'challenge': 'Manual regulatory reporting to BaFin consumed 3 weeks per quarter and was prone to reconciliation errors.', 'page': 'eng-02'}], 'approach': [{'approach': 'An automated reporting pipeline with lineage tracking and a reconciliation engine, replacing spreadsheet-based assembly.', 'page': 'eng-02'}], 'technology': [{'technologies': 'Python, Airflow, PostgreSQL, dbt', 'page': 'eng-02'}], 'outcomes': [{'outcomes': 'reporting cycle cut from 15 days to 3 days; reconciliation errors reduced 80%', 'page': 'eng-02'}]}, 'citations': [{'claim': 'reporting cycle cut from 15 days to 3 days', 'source_ref': 'closeout.pdf#page=4', 'page_ref': 'eng-02'}, {'claim': 'reconciliation errors reduced 80%', 'source_ref': 'closeout.pdf#page=4', 'page_ref': 'eng-02'}], 'client_named': True}
    llm_out={'context': 'The engagement involved [MISSING: client_type] in DE.', 'challenge': 'Manual regulatory reporting to BaFin consumed 3 weeks per quarter and was prone to reconciliation errors.', 'approach': 'BGTS implemented an automated reporting pipeline with lineage tracking and a reconciliation engine, replacing spreadsheet-based assembly.', 'technology': 'Python, Airflow, PostgreSQL, dbt.', 'outcomes': 'The reporting cycle was cut from 15 days to 3 days. Reconciliation errors were reduced 80%.İncome reduce 200%.'}
    chech_llm_output_with_source(mcs, llm_out)
