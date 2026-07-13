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


def verify(case_study, record):
    """Run every check. Returns a report (see spec section 4.2)."""
    problems = []
    problems += find_ungrounded_numbers(case_study, record)
    problems += find_consent_breaches(case_study, record)

    # TODO(Ömer) L3: unsupported_claim — split the prose into individual
    #   factual assertions and verify each one, not just the numbers.
    #   This is where your compiler background really pays off.

    return {
        "engagement_id": record["id"],
        "verdict": "BLOCK" if problems else "PASS",
        "problems": problems,
    }


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
