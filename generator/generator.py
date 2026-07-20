"""
GENERATOR — Taha

Engagement Record -> grounded case study.

    python -m generator.generator <record.json>  > case_study.json

See the Project Specification, sections 3, 4.1 and 7.
"""
import argparse
import json
import sys

from common.contract import load_record, client_label, has_outcomes
from common.llm import ask_for_json, GROUNDING_RULES

SYSTEM = """You write case studies for BGTS, a software consultancy that
serves banks.

""" + GROUNDING_RULES + """

Write five sections: context, challenge, approach, technology, outcomes.
Keep it factual and professional. No marketing language.
"""


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

    outcomes_text = (
        "; ".join(o["metric"] for o in record["outcomes"])
        if has_outcomes(record)
        else "[MISSING: no measurable outcome was recorded for this engagement]"
    )

    return {
        "engagement_id": record["id"],
        "title": f"{record['domain']} for {client_label(record)}",
        "sections": {
            "context": f"{client_label(record)} in {record['region']}.",
            "challenge": record["challenge"],
            "approach": record["solution"],
            "technology": ", ".join(record["technologies"]),
            "outcomes": outcomes_text,
        },
        "citations": [
            {"claim": o["metric"], "source_ref": o["source_ref"]}
            for o in record["outcomes"]
        ],
        "client_named": record["may_be_named"],
    }
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
    user_prompt = f"Record:\n{json.dumps(record, indent=2 , ensure_ascii=False)}\n\n"
    user_prompt += "Analyze the given record."

    response = ask_for_json(SYSTEM, user_prompt)
    return response

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
