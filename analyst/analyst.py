"""
ANALYST — Elif

Coverage and gap analysis over the engagement corpus.

    python -m analyst.analyst --coverage  > coverage.json
"""
import argparse
import json
import sys
from collections import Counter
import pandas as pd

from common.contract import load_corpus


def profile(corpus):

    df = pd.DataFrame(corpus)

    print(f"Shape:{df.shape}\n")
  

    print(df["domain"].value_counts().to_string())
    print("------------------------------------\n")
    print(df["region"].value_counts().to_string())
    print("------------------------------------\n")
    print(df["client_type"].value_counts().to_string())
    print("-------------------------------------\n")
    

    return {
        "total_engagements": len(df),
        "by_domain": df["domain"].value_counts().to_dict(),
        "by_region": df["region"].value_counts().to_dict(),
        "by_client_type": df["client_type"].value_counts().to_dict(),
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
