import sys
import json
import itertools
from collections import Counter
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.cluster.hierarchy import linkage, dendrogram
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

JSON_PATH = "caseforge-testdata/records/corpus.json"

try:
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
except FileNotFoundError:
    print(f"ERROR: '{JSON_PATH}' not found.")
    sys.exit(1)

df = pd.json_normalize(data)
print(f"Total records: {len(df)}")
print(df[["domain", "region", "client_type"]].head())


domain_counts = df["domain"].value_counts()

plt.figure(figsize=(8, max(3, len(domain_counts) * 0.5)))
sns.barplot(x=domain_counts.values, y=domain_counts.index, color="#2b3a67")
plt.xlabel("Project Count")
plt.ylabel("Domain")
plt.title("Engagement Count by Domain")
plt.xticks(range(0, int(max(domain_counts.values)) + 2))
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "01_domain_counts.png"), dpi=150)
plt.close()

domain_region = pd.crosstab(df["domain"], df["region"])

plt.figure(figsize=(8, max(3, len(domain_region) * 0.5)))
sns.heatmap(domain_region, annot=True, fmt="d", cmap="Blues", cbar=True)
plt.title("Domain x Region: Project Count")
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "02_domain_region_heatmap.png"), dpi=150)
plt.close()

domain_client = pd.crosstab(df["domain"], df["client_type"])

plt.figure(figsize=(12, 5))
sns.heatmap(domain_client, annot=True, fmt="d", cmap="Purples", cbar=False, linewidths=.5)
plt.title("Domain x Client Type Relationships", fontsize=14, pad=15)
plt.xlabel("Client Type", fontsize=11)
plt.ylabel("Domain", fontsize=11)
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "03_domain_clienttype_heatmap.png"), dpi=150)
plt.close()



tech_lists = df["technologies"].apply(lambda x: x if isinstance(x, list) else [])

pair_counts = Counter()
for techs in tech_lists:
    unique_techs = sorted(set(techs))
    for pair in itertools.combinations(unique_techs, 2):
        pair_counts[pair] += 1

all_techs = sorted(set(t for techs in tech_lists for t in techs))
co_matrix = pd.DataFrame(0, index=all_techs, columns=all_techs)

for (t1, t2), count in pair_counts.items():
    co_matrix.loc[t1, t2] = count
    co_matrix.loc[t2, t1] = count

for t in all_techs:
    co_matrix.loc[t, t] = sum(1 for techs in tech_lists if t in techs)

plt.figure(figsize=(max(6, len(all_techs) * 0.7), max(5, len(all_techs) * 0.6)))
sns.heatmap(co_matrix, annot=True, fmt="d", cmap="YlGnBu")
plt.title("Technology Co-occurrence Matrix\n(diagonal = total usage count)")
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "04_tech_cooccurrence_heatmap.png"), dpi=150)
plt.close()

print("\n--- Most Frequently Used Technology Pairs ---")
for pair, count in pair_counts.most_common(10):
    print(f"{pair[0]} + {pair[1]}: {count} projects")


# görselleştirme için kümeleme

from scipy.spatial.distance import pdist

cluster_features = df[["domain", "region", "client_type"]].copy()
df_encoded = pd.get_dummies(cluster_features)

jaccard_distances = pdist(df_encoded.values, metric="jaccard")
Z = linkage(jaccard_distances, method="average")

fig, ax = plt.subplots(figsize=(10, max(6, len(df) * 0.4)))
leaf_labels = df["domain"].astype(str) + " - " + df["client_type"].astype(str)

dendrogram(
    Z,
    labels=leaf_labels.values,
    orientation="right",
    leaf_font_size=10,
    color_threshold=0.5, 
    ax=ax,
)

ax.set_title("Project Archetypes — Hierarchical Clustering (Jaccard Distance)")
ax.set_xlabel("Jaccard Distance (0 = identical, 1 = entirely different)")
fig.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, "05_win_theme_clusters_dendrogram.png"), dpi=150)
plt.close(fig)

print(f"Dendrogram saved: {os.path.join(OUTPUT_DIR, '05_win_theme_clusters_dendrogram.png')}")


#K-Modes kümeleme(model eğitiminde kolaylık sağlayacak)
from kmodes.kmodes import KModes

print("\n--- K-Modes Clustering---")

categorical_data = df[["domain", "region", "client_type"]].astype(str)

N_CLUSTERS = 5  

km_model = KModes(n_clusters=N_CLUSTERS, init="Huang", n_init=5, random_state=42, verbose=0)
df["kmodes_cluster"] = km_model.fit_predict(categorical_data)

print(f"K-Modes cluster modes:")
centroids = pd.DataFrame(km_model.cluster_centroids_, columns=categorical_data.columns)
print(centroids.to_string(index=True))

print("\n--- K-Modes Cluster Summaries ---")
for c in sorted(df["kmodes_cluster"].unique()):
    sub = df[df["kmodes_cluster"] == c]
    print(f"\nCluster {c} ({len(sub)} projects): {list(sub['id'])}")
    print(f"  Domains     : {sub['domain'].value_counts().to_dict()}")
    print(f"  Client Types: {sub['client_type'].value_counts().to_dict()}")
    print(f"  Region'lar     : {sub['region'].value_counts().to_dict()}")

print("\nCharts saved: 01_domain_counts.png, 02_domain_region_heatmap.png, "
      "03_domain_clienttype_heatmap.png, 04_tech_cooccurrence_heatmap.png, "
      "05_win_theme_clusters_dendrogram.png")
