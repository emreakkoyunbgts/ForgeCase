"""
LIBRARIAN — Arda

RFP -> the engagements that best prove we can do the job.

    python -m librarian.librarian <rfp.txt>  > matches.json
"""
import argparse
import json
import sys

from common.contract import load_corpus
from common.errors import die


def searchable_text(record):
    """The text we embed for one engagement."""
    return " ".join([
        record["domain"], record["region"], record["client_type"],
        record["challenge"], record["solution"],
        " ".join(record["technologies"]),
    ])


def search(query, corpus, top_k=3):
    """
    Return the top_k engagements most relevant to the query.

    TODO(Arda) L1: replace this keyword count with real embeddings.
        - embed each record's searchable_text() into a vector
        - embed the query
        - use FAISS to find nearest neighbours
    TODO(Arda) L2: explain WHY each one matched.
    TODO(Arda) L3: synthesise a grounded capability statement — and hold
        yourself to the same no-invention rule as Taha's Generator.
    """
    # --- STUB: naive keyword overlap. It works. It is not good. -----------
    print("[librarian] STUB: keyword overlap, not embeddings", file=sys.stderr)
    words = {w.lower().strip(".,") for w in query.split() if len(w) > 4}

    scored = []
    for record in corpus:
        text = searchable_text(record).lower()
        score = sum(1 for w in words if w in text)
        scored.append((score, record))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "engagement_id": r["id"],
            "score": s,
            "why": "TODO(Arda): explain what actually matched",
        }
        for s, r in scored[:top_k]
    ]
    # ----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="RFP -> matching engagements")
    parser.add_argument("rfp", help="path to an RFP text file")
    parser.add_argument("--top", type=int, default=3)
    args = parser.parse_args()

    try:
        query = open(args.rfp, encoding="utf-8").read()
    except FileNotFoundError:
        die(f"no such file: {args.rfp}")

    matches = search(query, load_corpus(), args.top)
    json.dump({"matches": matches}, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
