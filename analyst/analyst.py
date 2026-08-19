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
from itertools import product

from common.contract import load_corpus


def profile(corpus):

    try:
        df = pd.DataFrame(corpus)
        if df.empty:
            return {"error": "No engagements found in corpus."}
        required_cols = ["domain", "region", "client_type"]
        for col in required_cols:
            if col not in df.columns:
                 df[col] = "Unknown" 
                 
    except Exception as e:
        print(f"ValueError: {e}")
        return {"error": "Failed to create DataFrame from corpus."}

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

def coverage_gaps(corpus, show_chart=True):

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

    gaps = sorted(
        (d, g)
        for d in domains
        for g in regions
        if (d, g) not in have
    )

    if show_chart:
        fig, ax = plt.subplots(figsize=(10, 6))

        for d in domains:
            for r in regions:
                combo = (d, r)

                if combo in gaps:
                    ax.scatter(
                        r,
                        d,
                        color="red",
                        marker="x",
                        s=100,
                        label="Gap",
                    )
                else:
                    if grid_data[combo]:
                        ax.scatter(
                            r,
                            d,
                            color="orange",
                            marker="^",
                            s=120,
                            label="No Outcome",
                        )
                    else:
                        ax.scatter(
                            r,
                            d,
                            color="green",
                            marker="o",
                            s=100,
                            label="Proof Point",
                        )

        ax.set_title(
            "Coverage Map: Domain x Region",
            fontweight="bold",
        )
        ax.set_xlabel("Region")
        ax.set_ylabel("Domain")
        ax.grid(True, linestyle="--", alpha=0.5)

        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))

        ax.legend(
            by_label.values(),
            by_label.keys(),
            bbox_to_anchor=(1.05, 1),
            loc="upper left",
        )

        plt.tight_layout()

        if "pytest" not in sys.modules:
            plt.show()

        plt.close()

    return [
        {"domain": d, "region": g}
        for d, g in gaps
    ]

def generate_action_list(corpus):
    df= pd.DataFrame(corpus)
    valid_domains = set(df["domain"].dropna().unique())
    valid_regions = set(df["region"].dropna().unique())
    existing_pairs = set(zip(df["domain"], df["region"]))

    domain_counts=df["domain"].value_counts().to_dict()
    region_counts=df["region"].value_counts().to_dict()

    prioritized_gaps = []
    for domain, region in product(valid_domains, valid_regions):
        if (domain, region) not in existing_pairs:
            domain_strength = domain_counts.get(domain, 0)
            region_strength = region_counts.get(region, 0)
            proximity_score = domain_strength + region_strength

            prioritized_gaps.append({
                "domain": domain,
                "region": region,
                "domain_experience": domain_strength,
                "region_experience": region_strength,
                "proximity_score": proximity_score,
            })

    prioritized_gaps.sort(key=lambda x: x["proximity_score"], reverse=True)
    if prioritized_gaps:
        sorted_scores = sorted(g["proximity_score"] for g in prioritized_gaps)
        n = len(sorted_scores)
        high_threshold = sorted_scores[int(n * 0.66)]
        medium_threshold = sorted_scores[int(n * 0.33)]
        for gap in prioritized_gaps:
            score = gap["proximity_score"]
            if score >= high_threshold:
                gap["priority"] = "HIGH"
            elif score >= medium_threshold:
                gap["priority"] = "MEDIUM"
            else:
                gap["priority"] = "LOW"

            d_exp = gap["domain_experience"]
            r_exp = gap["region_experience"]
            domain_name = gap["domain"]
            region_name = gap["region"]
            priority = gap["priority"]
 
            if priority == "HIGH":
                note = (
                        f"One engagement away from {region_name} {domain_name}: "
                        f"already delivered {domain_name} {d_exp}x elsewhere and "
                        f"worked in {region_name} {r_exp}x in other domains."
                    )
            elif priority == "MEDIUM":
                note = (
                        f"A few steps from {region_name} {domain_name}: some "
                        f"{domain_name} experience ({d_exp}x) and some presence in "
                        f"{region_name} ({r_exp}x), but not yet a strong combination."
                    )
            else:
                note = (
                    f"Lower-priority combination: only {d_exp}x {domain_name} "
                    f"experience and {r_exp}x presence in {region_name} overall — "
                    f"relatively weaker signal compared to other gaps."
                )
  
            gap["note"] = note

    chase_list = []
    for idx, row in df.iterrows():
        outcomes = row.get("outcomes")
        if not outcomes or (isinstance(outcomes, list) and len(outcomes) == 0):
            chase_list.append({
                "engagement_id": row.get("id", f"unknown-id-{idx}"),
                "client": row.get("client_type", "Unknown Client"),
                "reason": "Missing outcomes data.",
            })

    return {
        "ranked_gap_list": prioritized_gaps,
        "chase_list": chase_list,
    }

def main():
    parser = argparse.ArgumentParser(description="Coverage & gap analysis")
    parser.add_argument("--coverage", action="store_true")
    parser.add_argument("--recommend", action="store_true")
    args = parser.parse_args()

    corpus = load_corpus()
    result = profile(corpus)

    if args.coverage:
        result["gaps"] = coverage_gaps(corpus)
        print(f"[analyst] found {len(result['gaps'])} gaps in BGTS's proof points",
              file=sys.stderr)

    if args.recommend:
        recommendations = generate_action_list(corpus)
        with open("recommendations.json", "w", encoding="utf-8") as f:
            json.dump(recommendations, f, indent=4, ensure_ascii=False)
        print(f"[analyst] found {len(recommendations['ranked_gap_list'])} gaps, "
              f"{len(recommendations['chase_list'])} engagements missing outcomes — "
              f"written to recommendations.json", file=sys.stderr)


    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()

if __name__ == "__main__":
    main()
