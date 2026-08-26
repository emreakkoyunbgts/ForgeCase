"""
Engagement Analytics Dashboard (Streamlit)
streamlit run app.py

  - Domain / Region / Client Type dağılımı
  - Teknoloji co-occurrence
  - Win-theme clustering (Jaccard hiyerarşik + K-Modes)
"""

import json
import itertools
from collections import Counter

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st
from scipy.cluster.hierarchy import linkage, dendrogram
from scipy.spatial.distance import pdist
from kmodes.kmodes import KModes

st.set_page_config(page_title="Engagement Analytics", layout="wide")
st.title("Engagement Analytics Dashboard")

DEFAULT_PATH = "caseforge-testdata/records/corpus.json"

st.sidebar.header("Data Source")
uploaded_file = st.sidebar.file_uploader("Upload JSON file (optional)", type=["json"])
json_path = st.sidebar.text_input("or enter file path", value=DEFAULT_PATH)

@st.cache_data
def load_data(path: str, file_bytes: bytes | None):
    if file_bytes is not None:
        data = json.loads(file_bytes.decode("utf-8"))
    else:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    return pd.json_normalize(data)

try:
    file_bytes = uploaded_file.read() if uploaded_file is not None else None
    df = load_data(json_path, file_bytes)
except FileNotFoundError:
    st.error(f"'{json_path}' not found. Upload a file from the left sidebar or enter a valid path.")
    st.stop()
except Exception as e:
    st.error(f"Error occurred while reading data: {e}")
    st.stop()

st.sidebar.success(f"{len(df)} records loaded")
st.sidebar.header("Filters")
domain_filter = st.sidebar.multiselect("Domain", sorted(df["domain"].unique()))
region_filter = st.sidebar.multiselect("Region", sorted(df["region"].unique()))
client_filter = st.sidebar.multiselect("Client Type", sorted(df["client_type"].unique()))

filtered_df = df.copy()
if domain_filter:
    filtered_df = filtered_df[filtered_df["domain"].isin(domain_filter)]
if region_filter:
    filtered_df = filtered_df[filtered_df["region"].isin(region_filter)]
if client_filter:
    filtered_df = filtered_df[filtered_df["client_type"].isin(client_filter)]

if len(filtered_df) == 0:
    st.warning("No records match the filters.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Trends", "Technology Co-occurrence", " Win-Theme Clustering"])

with tab1:
    st.subheader("Engagement Count by Domain")

    domain_counts = filtered_df["domain"].value_counts()
    fig, ax = plt.subplots(figsize=(8, max(3, len(domain_counts) * 0.5)))
    sns.barplot(x=domain_counts.values, y=domain_counts.index, color="#28365D", ax=ax)
    ax.set_xlabel("Project Count")
    ax.set_ylabel("Domain")
    ax.set_xticks(range(0, int(max(domain_counts.values)) + 2))
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Domain x Region")
        domain_region = pd.crosstab(filtered_df["domain"], filtered_df["region"])
        fig, ax = plt.subplots(figsize=(6, max(3, len(domain_region) * 0.5)))
        sns.heatmap(domain_region, annot=True, fmt="d", cmap="Blues", cbar=True, ax=ax)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    with col2:
        st.subheader("Domain x Client Type")
        domain_client = pd.crosstab(filtered_df["domain"], filtered_df["client_type"])
        fig, ax = plt.subplots(figsize=(6, max(3, len(domain_client) * 0.5)))
        sns.heatmap(domain_client, annot=True, fmt="d", cmap="Purples", cbar=False, linewidths=.5, ax=ax)
        ax.set_xlabel("Client Type")
        ax.set_ylabel("Domain")
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    with st.expander("Show raw data"):
        st.dataframe(filtered_df[["id", "domain", "region", "client_type"]], use_container_width=True)


with tab2:
    st.subheader("Technology Combinations")

    tech_lists = filtered_df["technologies"].apply(lambda x: x if isinstance(x, list) else [])

    pair_counts = Counter()
    for techs in tech_lists:
        unique_techs = sorted(set(techs))
        for pair in itertools.combinations(unique_techs, 2):
            pair_counts[pair] += 1

    all_techs = sorted(set(t for techs in tech_lists for t in techs))

    if len(all_techs) == 0:
        st.info("No technology data available in the filtered records.")
    else:
        co_matrix = pd.DataFrame(0, index=all_techs, columns=all_techs)
        for (t1, t2), count in pair_counts.items():
            co_matrix.loc[t1, t2] = count
            co_matrix.loc[t2, t1] = count
        for t in all_techs:
            co_matrix.loc[t, t] = sum(1 for techs in tech_lists if t in techs)

        fig, ax = plt.subplots(figsize=(max(6, len(all_techs) * 0.7), max(5, len(all_techs) * 0.6)))
        sns.heatmap(co_matrix, annot=True, fmt="d", cmap="YlGnBu", ax=ax)
        ax.set_title("Diagonal = Total Usage Count")
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

        st.subheader("Most Frequently Used Technology Pairs")
        top_pairs = pd.DataFrame(
            [(f"{p[0]} + {p[1]}", c) for p, c in pair_counts.most_common(10)],
            columns=["Technology Pair", "Project Count"],
        )
        st.dataframe(top_pairs, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Natural Clusters")
    st.caption(
        "using categorical features: Domain + Region + Client Type."
    )

    if len(filtered_df) < 4:
        st.warning("Not enough records to perform clustering. At least 4 records are required.")
    else:
        cluster_features = filtered_df[["domain", "region", "client_type"]].copy()

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Jaccard Hierarchy Dendrogram**")

            df_encoded = pd.get_dummies(cluster_features)
            jaccard_distances = pdist(df_encoded.values, metric="jaccard")
            Z = linkage(jaccard_distances, method="average")

            leaf_labels = filtered_df["domain"].astype(str) + " - " + filtered_df["client_type"].astype(str)

            fig, ax = plt.subplots(figsize=(7, max(4, len(filtered_df) * 0.35)))
            dendrogram(
                Z,
                labels=leaf_labels.values,
                orientation="right",
                leaf_font_size=9,
                color_threshold=0.5,
                ax=ax,
            )
            ax.set_xlabel("Jaccard distance (0 = identical, 1 = entirely different)")
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

        with col2:
            st.markdown("**K-Modes Clustering**")
            st.caption("Scalable, model-based clustering for categorical data.")

            max_k = min(8, len(filtered_df) - 1)
            n_clusters = 5

            categorical_data = cluster_features.astype(str)
            km_model = KModes(n_clusters=n_clusters, init="Huang", n_init=5, random_state=42, verbose=0)
            cluster_labels = km_model.fit_predict(categorical_data)

            result_df = filtered_df.copy()
            result_df["cluster"] = cluster_labels

            summary_rows = []
            for c in sorted(result_df["cluster"].unique()):
                sub = result_df[result_df["cluster"] == c]
                top_domain = sub["domain"].value_counts().idxmax()
                top_client = sub["client_type"].value_counts().idxmax()
                top_region = sub["region"].value_counts().idxmax()
                summary_rows.append({
                    "Cluster": c,
                    "Project Count": len(sub),
                    "Weighted Domain": top_domain,
                    "Weighted Client Type": top_client,
                    "Weighted Region": top_region,
                })

            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        with st.expander("Show raw data with cluster labels"):
            st.dataframe(
                result_df[["id", "domain", "region", "client_type", "cluster"]],
                use_container_width=True,
                hide_index=True,
            )