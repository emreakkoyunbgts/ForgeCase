"""
ANALYST — Elif

Coverage and gap analysis over the engagement corpus.

    python -m analyst.analyst --coverage  > coverage.json
"""
import argparse
import json
import sys
from collections import Counter

from common.contract import load_corpus


def profile(corpus):
    """
    TODO(Elif) L1: do this properly with pandas.

        import pandas as pd
        df = pd.DataFrame(corpus)
        df["domain"].value_counts()

    Start by just LOOKING at the data. What is in it? What is uneven?
    """
    return {
        "total_engagements": len(corpus),
        "by_domain": dict(Counter(r["domain"] for r in corpus)),
        "by_region": dict(Counter(r["region"] for r in corpus)),
        "by_client_type": dict(Counter(r["client_type"] for r in corpus)),
        "no_outcome": [r["id"] for r in corpus if not r["outcomes"]],
    }


def coverage_gaps(corpus):
    """
    THE INTERESTING BIT. Which domain x region combinations have NO proof?

    TODO(Elif) L2:
      - build the full grid of domain x region
      - subtract the combinations we actually have
      - what's left is what BGTS CANNOT prove. That is the useful output.
      - then chart it (matplotlib)
    """
    domains = {r["domain"] for r in corpus}
    regions = {r["region"] for r in corpus}
    have = {(r["domain"], r["region"]) for r in corpus}

    gaps = sorted((d, g) for d in domains for g in regions if (d, g) not in have)

    return [{"domain": d, "region": g} for d, g in gaps]


def main():
    parser = argparse.ArgumentParser(description="Coverage & gap analysis")
    parser.add_argument("--coverage", action="store_true")
    args = parser.parse_args()

    corpus = load_corpus()
    result = profile(corpus)

    if args.coverage:
        result["gaps"] = coverage_gaps(corpus)
        print(f"[analyst] found {len(result['gaps'])} gaps in BGTS's proof points",
              file=sys.stderr)

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
