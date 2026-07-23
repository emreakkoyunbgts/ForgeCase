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
import matplotlib.pyplot as plt

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

    domains = sorted({r["domain"] for r in corpus})
    regions = sorted({r["region"] for r in corpus})
    
    grid_data = {}
    
    for r in corpus:
        combo = (r["domain"], r["region"])
        is_missing = not bool(r.get("outcomes"))
        
        if combo not in grid_data:
            grid_data[combo] = is_missing
        else:
            if is_missing:
                grid_data[combo] = True
    
    have = set(grid_data.keys())

    gaps = sorted((d, g) for d in domains for g in regions if (d, g) not in have)

    fig, ax = plt.subplots(figsize=(10, 6))
    
    for d in domains:
        for r in regions:
            combo = (d, r)
            if combo in gaps:
                ax.scatter(r, d, color="red", marker="x", s=100, label="Gap")
            else:
                if grid_data[combo]: 
                    ax.scatter(r, d, color="orange", marker="^", s=120, label="No Outcome")
                else:
                    ax.scatter(r, d, color="green", marker="o", s=100, label="Proof Point")

    
    ax.set_title("Coverage Map: Domain x Region", fontweight="bold")
    ax.set_xlabel("Region")
    ax.set_ylabel("Domain")
    ax.grid(True, linestyle="--", alpha=0.5)
    
    
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), bbox_to_anchor=(1.05, 1), loc='upper left')
    
    plt.tight_layout()

# pytest çalıştırılırsa grafiğin test sürecini bloklamaması için ekledim.
    if "pytest" not in sys.modules:
        plt.show()
    plt.close()

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
