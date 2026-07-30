"""Tests for Trends & Clustering"""
import json
import itertools
from collections import Counter
import pandas as pd
import pytest

def load_corpus_df():
    with open("caseforge-testdata/records/corpus.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return pd.json_normalize(data)

def test_finds_all_twelve_engagements():
    df = load_corpus_df()
    assert len(df) == 12

def test_domain_distribution_counts():
    df = load_corpus_df()
    counts = df["domain"].value_counts()
    
    assert counts["core banking"] == 3
    assert counts["data platform"] == 3
    assert counts["regulatory reporting"] == 2

def test_technology_cooccurrence_matrix():
    df = load_corpus_df()
    tech_lists = df["technologies"].apply(lambda x: x if isinstance(x, list) else [])
    
    pair_counts = Counter()
    for techs in tech_lists:
        unique_techs = sorted(set(techs))
        for pair in itertools.combinations(unique_techs, 2):
            pair_counts[pair] += 1

    assert pair_counts[("PostgreSQL", "Python")] == 3
    assert pair_counts[("Java", "Kafka")] == 3
    assert pair_counts[("Airflow", "dbt")] == 2

def test_clustering_features_ready():
    df = load_corpus_df()
    cluster_features = df[["domain", "region", "client_type"]].copy()
    df_encoded = pd.get_dummies(cluster_features)
    
    domain_cols = [col for col in df_encoded.columns if col.startswith("domain_")]
    assert len(domain_cols) == 5