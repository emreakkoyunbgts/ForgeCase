# Ömer Atilla - Verifier Setup (Sprint 1)
"""
VERIFIER — Ömer

THE GATE. Catches facts that were invented.

    python -m verifier.verifier <case_study.json> <record.json>

Exit 0 = PASS (nothing invented).
Exit 1 = BLOCK (something was invented). This is NOT a crash — it means you
         did your job. The Publisher refuses to run when you exit non-zero.

See the Project Specification, sections 4.2, 5.2 and 7.
"""
import argparse
import json
import re
import sys

from common.contract import load_record, all_source_facts
from common.errors import die, SUCCESS, REJECTED

# Including new modules that I write
from verifier.claim_parser import ClaimParser
from verifier.entailment_checker import EntailmentChecker

# Matches 45, 45%, 45.5, 2019 ...
NUMBER = re.compile(r"\d+(?:\.\d+)?%?")


def find_ungrounded_numbers(case_study, record):
    """
    Every number in the output MUST appear somewhere in the source record.
    Anything else was invented.

    TODO(Ömer) L1: this naive version works — make it better.
      - it currently misses "3 months" when the source says "11 months"
        (the number 3 might appear elsewhere and mask it)
      - it will falsely flag "6 hours" if the source writes it differently
      - L3: fuzzy match, so "45 percent" and "45%" are the same claim
    """
    text = json.dumps(case_study.get("sections", {}), ensure_ascii=False)
    in_output = set(NUMBER.findall(text))
    in_source = set(NUMBER.findall(all_source_facts(record)))

    return [
        {
            "type": "ungrounded_number",
            "value": value,
            "why": "this figure does not appear anywhere in the source record",
        }
        for value in sorted(in_output - in_source)
    ]


def find_consent_breaches(case_study, record):
    """
    The client's REAL name must not appear unless may_be_named is true.

    TODO(Ömer) L2: this is the confidentiality check. Get it right — a leak
    here is the most serious defect anyone on this project can ship.
    """
    """
    ############ OLD VERSION #######################
    if record.get("may_be_named") is True:
        return []

    text = json.dumps(case_study, ensure_ascii=False)
    if record["client"] in text:
        return [{
            "type": "client_named_without_consent",
            "value": record["client"],
            "why": "may_be_named is false — this client must be anonymised",
        }]
    return []
    """
    ############ NEW VERSION #######################
    """
    The client's REAL name must not appear unless may_be_named is true
    Uses EntailmentChecker for robust validation
    """
    checker = EntailmentChecker()
    may_be_named = record.get("may_be_named", True)
    client_name = record.get("client", record.get("client_name"))

    draft_text = json.dumps(case_study, ensure_ascii=False)

    if not checker.verify_client_naming(draft_text, client_name, may_be_named):
        return [{
            "type": "client_named_without_consent",
            "value": client_name,
            "why": "may_be_named is false - this client must be anonymised",
        }]
    return []

def find_unsupported_claims(case_study, record):
    """
    CF-58 & CF-59: Extracts factual claims and verifies them against ground truth record outcomes.
    """
    """
    ############# OLD VERSION #####################
    parser = ClaimParser()
    checker = EntailmentChecker()

    draft_text = json.dumps(case_study.get("sections", {}), ensure_ascii=False)
    extracted_claim = parser.extract_claims(draft_text)
    record_outcomes = record.get("outcomes", [])

    if not checker.verify_metrics(extracted_claims, record_outcomes):
        return [{
            "type": "unsupported_claim",
            "value": extracted_claims,
            "why": "one or more extracted claims are not supported by record outcomes",
        }]
    
    return []
    """
    ############## NEW VERSION ####################
    parser = ClaimParser()
    checker = EntailmentChecker()
    
    # 1. Giving all case_study JSON data to parse_case_study
    extracted_claim_objs = parser.parse_case_study(case_study)

    """
    # 2. Just getting metric/quantitative claims texts
    extracted_claims = [
        c.get("raw_text", "")
        for c in extracted_claim_objs
        if isinstance(c, dict) and c.get("type") == "metric_claim"
    ]
    """

    record_outcomes = record.get("outcomes", [])
    problems = []

    # --- L1-L2-L3 Tasks: Numerical Metric Controls ---
    for c in extracted_claim_objs:
        if isinstance(c, dict) and c.get("type") == "metric_claim":
            target_val = c.get("target_value", "")
            raw_text = c.get("raw_text", "")

            # Don't counting terms like "Tier-1" customers / general degree terms as fake number
            if "tier-" in raw_text.lower():
                continue
            
            if not checker.verify_metrics([raw_text], record_outcomes):
                problems.append({
                    "type": "unsupported_claim",
                    "value": target_val if target_val else raw_text,
                    "why": "this claim metric is not suported by record outcomes",
                })

            # --- L4: Exaggeration/fabrication check based on the parsed claim text ---
            l4_problems = checker.check_paraphrased_claims(raw_text, record)
            problems.extend(l4_problems)
        
    # --- L4 (Additional Safety Valve): If there is an unparsed general text block ---
    # case_study can be a dict or a string; we take the general text and run it through the check
    full_text = json.dumps(case_study, ensure_ascii=False) if isinstance(case_study, dict) else str(case_study)

    # If no L4 issues were found during the loop, we also check the general text block once
    if not any(p.get("type") == "unsupported_qunlitative_claim" for p in problems):
        general_l4_problems = checker.check_paraphrased_claims(full_text, record)
        problems.extend(general_l4_problems)

    return problems

def verify(case_study, record):
    """Run every check. Returns a report (see spec section 4.2)."""
    problems = []
    problems += find_ungrounded_numbers(case_study, record)
    problems += find_consent_breaches(case_study, record)
    # 3. CF-58 & CF-59 Claim Parsing and Entailment Control
    problems += find_unsupported_claims(case_study, record)

    # TODO(Ömer) L3: unsupported_claim — split the prose into individual
    #   factual assertions and verify each one, not just the numbers.
    #   This is where your compiler background really pays off.

    return {
        "engagement_id": record["id"],
        "verdict": "BLOCK" if problems else "PASS",
        "problems": problems,
    }

def normalize_text(text: str) -> str:
    """
    Converts the text into lower case and dynamically matches different unit/percentage texts
    and converts them into a standart form 
    """
    if not text:
        return ""

    text = text.lower()

    # Converts the 'percentage' or 'yüzde' to '%' symbol[cite: 1, 3]
    text = re.sub(r'\b(percent|per cent)\b', '%', text)

    # Removes the gaps between number and the % ('45 %' -> '45%')
    text = re.sub(r'(\d+)\s*%', r'\1%', text)

    # Standardizing the time units
    text = re.sub(r'\b(hours | hour | hrs | hr | h)\b', 'hours', text)
    text = re.sub(r'\b(minutes | minute | mins | min | m)\b', 'minutes', text)

    return text

def extract_grounded_tokens(text: str) -> set:
    """
    Extracts every number, percentage and date pattern as a normalized form set[cite: 1, 3]   
    """
    normalized = normalize_text(text)

    # Numbers, percentages and numeric patterns[cite: 1, 3]
    tokens = set(re.findall(r'\d+(?:\.\d+)?%?', normalized))
    return tokens

def main():
    parser = argparse.ArgumentParser(description="Catch invented facts")
    parser.add_argument("case_study", help="the generated case study")
    parser.add_argument("record", help="the source record it must be grounded in")
    args = parser.parse_args()

    try:
        with open(args.case_study, encoding="utf-8") as f:
            case_study = json.load(f)
    except FileNotFoundError:
        die(f"no such file: {args.case_study}")
    except json.JSONDecodeError as e:
        die(f"{args.case_study} is not valid JSON: {e}")

    record = load_record(args.record)
    report = verify(case_study, record)

    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    print()

    if report["verdict"] == "BLOCK":
        print(f"\n[verifier] BLOCKED — {len(report['problems'])} problem(s) found",
              file=sys.stderr)
        for p in report["problems"]:
            print(f"    {p['type']}: {p['value']} — {p['why']}", file=sys.stderr)
        sys.exit(REJECTED)

    print("[verifier] PASS — every claim is grounded", file=sys.stderr)
    sys.exit(SUCCESS)


if __name__ == "__main__":
    main()
