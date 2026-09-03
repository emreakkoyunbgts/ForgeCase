"""
GENERATOR — Taha

Engagement Record -> grounded case study.

    python -m generator.generator <record.json>  > case_study.json

See the Project Specification, sections 3, 4.1 and 7.
"""
import argparse
import json
import sys

import os
import time



from common.contract import load_record, client_label, has_outcomes
from common.llm import ask_for_json, GROUNDING_RULES

import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("generator.log",encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])

logger=logging.getLogger(__name__)





SYSTEM_CHECK="""
you are a text comprator, there is rules; 
""" + GROUNDING_RULES + """

I am gone give you 2 json document one is source which is multi source case ,
another is text to be checked which is LLM output,
don't Text correction! Only remove incorrect or fabricated information.
Do not add any text or information.just compare with source json .
"""


SYSTEM = """You write case studies for BGTS, a software consultancy that
serves banks.

""" + GROUNDING_RULES + """

Write five sections: context, challenge, approach, technology, outcomes.
Keep it factual and professional. No marketing language.
"""

SYSTEM_GERMAN = """You write case studies for BGTS, a software consultancy that
serves banks.

""" + GROUNDING_RULES + """

Write five sections: context, challenge, approach, technology, outcomes.
Keep it factual and professional. No marketing language.
Then translate the case study into German.Fieald names should remain in English,
but the content should be translated into German.
"""

SYSTEM_TURKISH = """You write case studies for BGTS, a software consultancy that
serves banks.

""" + GROUNDING_RULES + """

Write five sections: context, challenge, approach, technology, outcomes.
Keep it factual and professional. No marketing language.
Then translate the case study into Turkish.Fieald names should remain in English,
but the content should be translated into Turkish.
"""



SYSTEM_TAHA="""You are a analytical AI assistant that generates case studies for BGTS, 
a software consultancy that serves banks.


""" + GROUNDING_RULES + """
Write five sections: context, challenge, approach, technology, outcomes.
Write with highlighting the developed features .
Keep it factual and professional. No marketing language.

"""

SYSTEM_CONCISE = """You write case studies for BGTS, a software consultancy that
serves banks.

""" + GROUNDING_RULES + """

Write five sections: context, challenge, approach, technology, outcomes.

Tone:
- Concise and direct.
- Use short paragraphs and straightforward wording.
- Prioritize clarity over detail.
- Keep every sentence information-dense.

The requested tone must never override the grounding rules.
"""

SYSTEM_PUNCHY = """You write case studies for BGTS, a software consultancy that
serves banks.

""" + GROUNDING_RULES + """

Write five sections: context, challenge, approach, technology, outcomes.

Tone:
- Crisp and engaging while remaining professional.
- Vary sentence structure to improve readability.
- Prefer active voice.
- Make the narrative flow naturally without adding facts.
- Never exaggerate impact or use promotional language.

The requested tone must never override the grounding rules.
"""






def save_llm_output_as_json(llm_output: dict,
                            case_study_id: str,
                            output_dir: str = "generator_llm_output_json") -> str:
    """
    Saves a generated case study dictionary as a JSON file.

    Returns:
        Path to the saved JSON file.
    """
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, f"{case_study_id}.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            llm_output,
            f,
            indent=4,
            ensure_ascii=False
        )

    return output_path








def render_outcomes(record):
    outcomes = record.get("outcomes")

    if not outcomes:
        return "[MISSING: no measurable outcome was recorded for this engagement]"

    parts = []

    for outcome in outcomes:
        metric = outcome.get("metric")

        if not metric:
            parts.append("[MISSING: outcome metric]")
        else:
            parts.append(metric)

    return "; ".join(parts)


def render_citations(record):
    citations = []

    for outcome in record.get("outcomes", []):

        metric = outcome.get("metric")
        source_ref = outcome.get("source_ref")

        if not metric:
            citations.append({
                "claim": "[MISSING: outcome metric]",
                "source_ref": "[MISSING: source reference required]"
            })

        if not source_ref:
            citations.append({
                "claim": metric,
                "source_ref": "[MISSING: source reference required]"
            })
        else:
            citations.append({
                "claim": metric,
                "source_ref": source_ref
            })

    return citations

def render_challenge(record):
    return (
        record.get("challenge")
        or "[MISSING: challenge description]"
    )

def render_solution(record):
    return (
        record.get("solution")
        or "[MISSING: solution description]"
    )

def render_technology(record):
    technologies = record.get("technologies")

    if not technologies:
        return "[MISSING: technologies used]"

    return ", ".join(technologies)

def render_team_size(record):
    return (
        str(record["team_size"])
        if record.get("team_size") is not None
        else "[MISSING: team size]"
    )

def render_title(record):
    domain = record.get("domain")

    if not domain:
        domain = "[MISSING: domain]"

    return f"{domain} for {client_label(record)}"

def render_context(record):
    region = record.get("region") or "[MISSING: region]"

    return f"{client_label(record)} in {region}."

###
######THIS AREA IS FOR MULTI-SOURCE CASE STUDY GENERATION######
###




def render_multi_source_citations(record,id):
    citations = []

    for outcome in record.get("outcomes", []):

        metric = outcome.get("metric")
        source_ref = outcome.get("source_ref")

        if not metric:
            citations.append({
                "claim": "[MISSING: outcome metric]",
                "source_ref": "[MISSING: source reference required]",
                "page_ref": id
            })

        if not source_ref:
            citations.append({
                "claim": metric,
                "source_ref": "[MISSING: source reference required]",
                "page_ref": id
            })
        else:
            citations.append({
                "claim": metric,
                "source_ref": source_ref,
                "page_ref": id
            })

    return citations

def render_multi_source_outcomes(record,id):
    return {
        "outcomes":render_outcomes(record),
        "page" : id
    }
def render_multi_source_technology(record,id):
    return {
        "technologies":render_technology(record),
        "page" : id
    }
def render_multi_source_solution(record,id):
    return {
        "approach": record.get("solution") or "[MISSING: solution description]",
        "page" : id
    }
def render_multi_source_challenge(record,id):
    return {
        "challenge": record.get("challenge") or "[MISSING: challenge description]",
        "page" : id
    }

def render_multi_source_tite(record,name,id):
    domain = record.get("domain")

    if not domain:
        domain = "[MISSING: domain]"

    return {
        "title": f"{domain} for {name}",
        "page" : id
    }
def render_multi_source_context(record,name,id):
    region = record.get("region") or "[MISSING: region]"

    return {
        "region": f"{name} in {region}.",
        "page" : id
    }



def client_may_be_named(record):
    return record.get("may_be_named", False)

def generate_two_source(record1 , record2):
    r1_id = record1.get("id", "[MISSING: engagement id]")
    r2_id = record2.get("id", "[MISSING: engagement id]")
    may_be=client_may_be_named(record1) and client_may_be_named(record2)
    r1_name=""
    r2_name=""
    if(may_be):
        r1_name=record1.get("client", "[MISSING: client name]")
        r2_name=record2.get("client", "[MISSING: client name]")
    else:
        r1_name=record1.get("client_type", "[MISSING: client type]")
        r2_name=record2.get("client_type", "[MISSING: client type]")

    if r1_name != r2_name:
        print(f"[generator] WARNING: The two records have different client names/types: {r1_name} vs {r2_name}", file=sys.stderr)
    tcs = {
        "engagement_ids": [r1_id, r2_id],
        "titlies" : [render_multi_source_tite(record1,r1_name,r1_id), render_multi_source_tite(record2,r2_name,r2_id)],
        "sections": {
            "context": [render_multi_source_context(record1,r1_name,r1_id), render_multi_source_context(record2,r2_name,r2_id)],
            "challenge": [render_multi_source_challenge(record1,r1_id), render_multi_source_challenge(record2,r2_id)],
            "approach": [render_multi_source_solution(record1,r1_id), render_multi_source_solution(record2,r2_id)],
            "technology": [render_multi_source_technology(record1,r1_id), render_multi_source_technology(record2,r2_id)],
            "outcomes": [render_multi_source_outcomes(record1,r1_id), render_multi_source_outcomes(record2,r2_id)],
        },
        "citations": render_multi_source_citations(record1,r1_id) + render_multi_source_citations(record2,r2_id),
        "client_named": may_be,
    }


    return tcs




def generate_multi_source(records):
    start_time = time.perf_counter()
    if not records:
        logger.error("records list cannot be empty")
        raise ValueError("records list cannot be empty")

    engagement_ids = [
        record.get("id", "[MISSING: engagement id]")
        for record in records
    ]

    may_be = all(client_may_be_named(record) for record in records)
    logger.info(f"Client may be named: {may_be}")
    client_names = []

    for record in records:
        if may_be:
            client_names.append(
                record.get("client", "[MISSING: client name]")
            )
        else:
            client_names.append(
                record.get("client_type", "[MISSING: client type]")
            )

    domain1 = records[0].get("domain", "[MISSING: domain]")
    for record in records[1:]:
        domain = record.get("domain", "[MISSING: domain]")
        if domain != domain1:
            logger.warning(f"Different domains found: {domain1} vs {domain}")


    if len(set(client_names)) > 1:
        logger.warning(f"Different client names/types found: {client_names}")


    tcs = {
        "engagement_ids": engagement_ids,

        "titles": [
            render_multi_source_tite(record, client_name, engagement_id)
            for record, client_name, engagement_id in zip(
                records,
                client_names,
                engagement_ids,
            )
        ],

        "sections": {
            "context": [
                render_multi_source_context(record, client_name, engagement_id)
                for record, client_name, engagement_id in zip(
                    records,
                    client_names,
                    engagement_ids,
                )
            ],

            "challenge": [
                render_multi_source_challenge(record, engagement_id)
                for record, engagement_id in zip(records, engagement_ids)
            ],

            "approach": [
                render_multi_source_solution(record, engagement_id)
                for record, engagement_id in zip(records, engagement_ids)
            ],

            "technology": [
                render_multi_source_technology(record, engagement_id)
                for record, engagement_id in zip(records, engagement_ids)
            ],

            "outcomes": [
                render_multi_source_outcomes(record, engagement_id)
                for record, engagement_id in zip(records, engagement_ids)
            ],
        },

        "citations": [
            citation
            for record, engagement_id in zip(records, engagement_ids)
            for citation in render_multi_source_citations(record, engagement_id)
        ],

        "client_named": may_be,
    }




    end_time=time.perf_counter()
    logger.info(f"Multi-source case study generation time: {end_time-start_time:.2f} seconds")

    return tcs









def generate(record):
    """
    Turn a record into a case study.

    TODO(Taha) L1: prompt the LLM with the record, get the five sections back.
    TODO(Taha) L2: enforce grounding.
        - if has_outcomes(record) is False, the outcomes section MUST say
          something like "[MISSING: no measurable outcome recorded]" and MUST
          NOT contain a number. This is the single most important test in the
          project — eng-12 exists precisely to catch you inventing one.
        - ALWAYS use client_label(record), never record["client"] directly.
    TODO(Taha) L3: add citations[] linking each claim to its source_ref.
    """
    # --- STUB: replace me -------------------------------------------------
    print(f"[generator] STUB: fabricating nothing, echoing the record",
          file=sys.stderr)
    """
    outcomes_text = (
        "; ".join(o["metric"] for o in record["outcomes"])
        if has_outcomes(record)
        else "[MISSING: no measurable outcome was recorded for this engagement]"
    )
    """
    cs={
        "engagement_id":  record.get("id", "[MISSING: engagement id]"),
        "title": render_title(record),
        "sections": {
            "context": render_context(record),
            "challenge": render_challenge(record),
            "approach": render_solution(record),
            "technology": render_technology(record),
            "outcomes": render_outcomes(record),
        },
        "citations": render_citations(record),
        "client_named": record.get("may_be_named", False),
    }

    return cs
    # ----------------------------------------------------------------------

def get_five_sections_with_llm(record):
    """
    Use the LLM to generate the five sections of a case study.

    This is the core of the generator. It is a single LLM call, with a
    system prompt that enforces grounding and a user prompt that contains
    the record.

    The LLM must return JSON with five sections: context, challenge, approach,
    technology, outcomes. Each section must be grounded in the record.
    """
    start_time=time.perf_counter()
    user_prompt = f"Record:\n{json.dumps(record, indent=2 , ensure_ascii=False)}\n\n"
    user_prompt += "Analyze the given record."

    response = ask_for_json(SYSTEM, user_prompt)
    logger.info(f"LLM response: {response}")

    end_time=time.perf_counter()
    logger.info(f"LLM processing time: {end_time-start_time:.2f} seconds")

    json_path=save_llm_output_as_json(response,record["engagement_ids"])
    logger.info(f"LLM output saved to JSON: {json_path}")

    return response


def get_llm_output_german(mcs:dict):
    start_time=time.perf_counter()
    user_prompt = f"Record:\n{json.dumps(mcs, indent=2, ensure_ascii=False)}\n\n"
    user_prompt += "Analyze the given record.just return the german translation."

    response=ask_for_json(SYSTEM_GERMAN, user_prompt)
    logger.info(f"LLM German response: {response}")

    end_time = time.perf_counter()
    logger.info(f"LLM processing time: {end_time - start_time:.2f} seconds")

    return response


def get_llm_output_turkish(mcs: dict):
    start_time = time.perf_counter()
    user_prompt = f"Record:\n{json.dumps(mcs, indent=2, ensure_ascii=False)}\n\n"
    user_prompt += "Analyze the given record.just return the turkish translation."

    response = ask_for_json(SYSTEM_TURKISH, user_prompt)
    logger.info(f"LLM Turkish response: {response}")

    end_time = time.perf_counter()
    logger.info(f"LLM processing time: {end_time - start_time:.2f} seconds")

    return response


def get_llm_punchy(mcs: dict):
    start_time=time.perf_counter()
    user_prompt = f"Multi-source case study:\n{json.dumps(mcs, indent=2, ensure_ascii=False)}\n\n"
    user_prompt += "Analyze the given multi-source case study and provide a punchy summary."

    response =ask_for_json(SYSTEM_PUNCHY, user_prompt)
    logger.info(f"LLM punchy response: {response}")

    end_time=time.perf_counter()
    logger.info(f"LLM punchy processing time: {end_time-start_time:.2f} seconds")

    json_path=save_llm_output_as_json(response, ",".join(mcs["engagement_ids"])+"_punchy")
    logger.info(f"LLM punchy output saved to JSON: {json_path}")


    return response


def get_llm_concise(mcs: dict):
    start_time=time.perf_counter()
    user_prompt = f"Multi-source case study:\n{json.dumps(mcs, indent=2, ensure_ascii=False)}\n\n"
    user_prompt += "Analyze the given multi-source case study and provide a concise summary."

    response = ask_for_json(SYSTEM_CONCISE, user_prompt)
    logger.info(f"LLM concise response: {response}")

    end_time=time.perf_counter()
    logger.info(f"LLM concise processing time: {end_time-start_time:.2f} seconds")

    json_path=save_llm_output_as_json(response, ",".join(mcs["engagement_ids"])+"_concise")
    logger.info(f"LLM concise output saved to JSON: {json_path}")

    return response


def chech_llm_output_with_source(mcs, llm_output):
    start_time=time.perf_counter()
    user_promt = f"Multi-source case study:\n{json.dumps(mcs, indent=2, ensure_ascii=False)}\n\n"
    user_promt += f"LLM output:\n{json.dumps(llm_output, indent=2, ensure_ascii=False)}\n\n"
    user_promt += "Compare the LLM output with the multi-source case study and remove any incorrect or fabricated information. "


    response=ask_for_json(SYSTEM_CHECK, user_promt)
    logger.info(f"LLM check response: {response}")

    end_time=time.perf_counter()
    logger.info(f"LLM check processing time: {end_time-start_time:.2f} seconds")

    json_path=save_llm_output_as_json(response, ",".join(mcs["engagement_ids"])+"_check")
    logger.info(f"LLM check output saved to JSON: {json_path}")

    return response


def generate_single_stream(records):

    mcs=generate_multi_source(records)
    llm_out=get_five_sections_with_llm(mcs)
    last_output=chech_llm_output_with_source(mcs,llm_out)

    return last_output

def generate_one_source_single_stream_case_study(record):
    mcs=generate_multi_source([record])
    llm_out=get_five_sections_with_llm(mcs)
    last_output=chech_llm_output_with_source(mcs,llm_out)


    return mcs



def main():
    parser = argparse.ArgumentParser(description="Record -> case study")
    parser.add_argument("record", help="path to an engagement record")
    args = parser.parse_args()

    record = load_record(args.record)
    case_study = generate(record)

    json.dump(case_study, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
