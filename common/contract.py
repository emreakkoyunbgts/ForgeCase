"""
THE CONTRACT.

This is the one thing all eight programs agree on. Every program either
produces an Engagement Record or consumes one.

DO NOT change this file on your own. Changing a field name here breaks
other people's programs, and they will find out at the worst possible
moment. Propose the change in standup first.

See the Project Specification, section 3.
"""
import json
from pathlib import Path

from common.errors import die

# Every field the contract requires.
REQUIRED_FIELDS = [
    "id", "client", "client_type", "may_be_named", "domain", "region",
    "challenge", "solution", "technologies", "outcomes",
]

VALID_REGIONS = {"UK", "DE", "NL", "TR", "GCC"}


def load_record(path):
    """Load one Engagement Record from disk. Dies cleanly if it can't."""
    try:
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
    except FileNotFoundError:
        die(f"no such file: {path}")
    except json.JSONDecodeError as e:
        die(f"{path} is not valid JSON: {e}")

    missing = [f for f in REQUIRED_FIELDS if f not in record]
    if missing:
        die(f"{path} is missing required field(s): {', '.join(missing)}")

    return record


def load_corpus(path="caseforge-testdata/records/corpus.json"):
    """Load all 12 engagement records."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        die(f"corpus not found at {path} — did you unzip the test data?")


def load_seed(engagement_id="eng-01"):
    """
    Load one of the 3 hand-written seed records.

    THIS IS WHY NOBODY WAITS FOR ANYBODY. You can build your program against
    a seed record on day one, before anyone else has written a line of code.
    """
    path = f"caseforge-testdata/records/seed/{engagement_id}.json"
    return load_record(path)


def save_record(record, path):
    """Write an Engagement Record to disk."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)


def client_label(record):
    """
    CONFIDENTIALITY. Use this EVERY time you print a client.

    The safe path is the default path: you get the anonymous label unless
    consent has been explicitly recorded. You have to do extra work to name
    a client, never less.

        eng-01 (may_be_named: false)  ->  "Tier-1 GCC retail bank"
        eng-02 (may_be_named: true)   ->  "Nordbank Deutschland"
    """
    if record.get("may_be_named") is True:
        return record["client"]
    return record["client_type"]


def has_outcomes(record):
    """True if this engagement has at least one measurable outcome."""
    return bool(record.get("outcomes"))


def all_source_facts(record):
    """
    Every fact the source actually supports, as one blob of text.

    The Generator and the Verifier both need this: the Generator to know what
    it is allowed to say, and the Verifier to check what was said.
    """
    return json.dumps(record, ensure_ascii=False)
