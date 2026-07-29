"""
LIBRARIAN — Arda

RFP -> the engagements that best prove we can do the job.

    python -m librarian.librarian <rfp.txt>  > matches.json
"""
import argparse
import json
import math
import re
import sys
from collections import Counter

from common.contract import load_corpus
from common.errors import die

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

def searchable_text(record):
    """The text we embed for one engagement."""
    return " ".join([
        record["domain"], record["region"], record["client_type"],
        record["challenge"], record["solution"],
        " ".join(record["technologies"]),
    ])

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TOKEN_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9+.#/-]*",
    re.IGNORECASE,
)

def load_embedding_model():
    """
    Load the sentence embedding model.
    """
    return SentenceTransformer(MODEL_NAME)

def embed_texts(model, texts):
    """
    Convert text strings into normalized FAISS-ready vectors.

    normalize_embeddings=True means FAISS inner-product search behaves like
    cosine similarity.
    """
    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embeddings.astype("float32")

def embed_engagement_records(corpus, model):
    """
    Embed every engagement record using searchable_text(record).
    """
    texts = [searchable_text(record) for record in corpus]
    return embed_texts(model, texts)


def build_engagement_index(embeddings):
    """
    Build a FAISS index containing one vector per engagement record.
    """
    if embeddings.ndim != 2:
        die("engagement embeddings must be a 2D matrix")

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    return index

def explanation_candidates(record):
    """
    Return public, structured fields that can explain why a record matched.

    The real client name is deliberately excluded.
    """
    candidates = []

    def add_candidate(label, value):
        if isinstance(value, str) and value.strip():
            candidates.append((label, value.strip()))

    add_candidate("domain", record.get("domain"))
    add_candidate("region", record.get("region"))
    add_candidate("client type", record.get("client_type"))

    for technology in record.get("technologies", []):
        add_candidate("technology", technology)

    return candidates

def explain_match(query_embedding, record, model, max_reasons=3):
    """
    Explain a match using the record fields most semantically similar
    to the RFP query.

    All returned values come directly from the engagement record.
    """
    candidates = explanation_candidates(record)

    if not candidates:
        return "Matched by overall semantic similarity."

    candidate_values = [
        value
        for _, value in candidates
    ]

    candidate_embeddings = embed_texts(model, candidate_values)

    # query_embedding has shape (1, dimensions), so [0] selects
    # the single query vector.
    similarities = candidate_embeddings @ query_embedding[0]

    ranked_indices = np.argsort(similarities)[::-1]

    reasons = []
    seen_values = set()

    for candidate_index in ranked_indices:
        label, value = candidates[int(candidate_index)]

        normalized_value = value.casefold()
        if normalized_value in seen_values:
            continue

        seen_values.add(normalized_value)
        reasons.append(f"{label}: {value}")

        if len(reasons) == max_reasons:
            break

    return "Matched on " + "; ".join(reasons)

def unique_strings(values):
    """
    Return unique, non-empty strings while preserving their original order.
    """
    result = []
    seen = set()

    for value in values:
        if not isinstance(value, str):
            continue

        cleaned = value.strip()
        if not cleaned:
            continue

        normalized = cleaned.casefold()
        if normalized in seen:
            continue

        seen.add(normalized)
        result.append(cleaned)

    return result


def format_list(values):
    """
    Format a list as:
    - A
    - A and B
    - A, B, and C
    """
    if not values:
        return ""

    if len(values) == 1:
        return values[0]

    if len(values) == 2:
        return f"{values[0]} and {values[1]}"

    return f"{', '.join(values[:-1])}, and {values[-1]}"


def build_capability_statement(
    matches,
    corpus,
    max_technologies=5,
    max_outcomes=3,
):
    """
    Build a grounded capability statement from retrieved engagements.

    Every fact in the output comes directly from the selected engagement
    records. Real client names are never included.
    """
    records_by_id = {
        record["id"]: record
        for record in corpus
    }

    selected_records = []

    for match in matches:
        engagement_id = match.get("engagement_id")
        record = records_by_id.get(engagement_id)

        if record is not None:
            selected_records.append(record)

    if not selected_records:
        return {
            "text": "No relevant engagement evidence was found.",
            "evidence": [],
        }

    domains = unique_strings(
        record.get("domain")
        for record in selected_records
    )

    regions = unique_strings(
        record.get("region")
        for record in selected_records
    )

    technologies = unique_strings(
        technology
        for record in selected_records
        for technology in record.get("technologies", [])
    )[:max_technologies]

    sentences = []
    evidence = []

    if domains:
        sentences.append(
            "The retrieved engagements provide evidence of BGTS work in "
            f"{format_list(domains)}."
        )

        for record in selected_records:
            domain = record.get("domain")

            if domain in domains:
                evidence.append({
                    "engagement_id": record["id"],
                    "field": "domain",
                    "value": domain,
                })

    if regions:
        sentences.append(
            "The relevant engagement evidence covers "
            f"{format_list(regions)}."
        )

        for record in selected_records:
            region = record.get("region")

            if region in regions:
                evidence.append({
                    "engagement_id": record["id"],
                    "field": "region",
                    "value": region,
                })

    if technologies:
        sentences.append(
            "Relevant technologies include "
            f"{format_list(technologies)}."
        )

        for record in selected_records:
            for technology in record.get("technologies", []):
                if technology in technologies:
                    evidence.append({
                        "engagement_id": record["id"],
                        "field": "technology",
                        "value": technology,
                    })

    documented_outcomes = []

    for record in selected_records:
        for outcome in record.get("outcomes", []):
            metric = outcome.get("metric")
            source_ref = outcome.get("source_ref")

            # Outcomes without a source cannot be used in grounded output.
            if not metric or not source_ref:
                continue

            documented_outcomes.append(metric)

            evidence.append({
                "engagement_id": record["id"],
                "field": "outcome",
                "value": metric,
                "source_ref": source_ref,
            })

            if len(documented_outcomes) == max_outcomes:
                break

        if len(documented_outcomes) == max_outcomes:
            break

    if documented_outcomes:
        sentences.append(
            "Documented outcomes include: "
            f"{'; '.join(documented_outcomes)}."
        )

    return {
        "text": " ".join(sentences),
        "evidence": evidence,
    }

def search(query, corpus, top_k=3):
    """
    Return the top_k engagements most relevant to the query.

    L1:
        - embed each engagement record
        - embed the RFP query
        - use FAISS to find nearest neighbours

    L2:
        - explain each result using structured fields from the record

    L3:
        - build a grounded capability statement from the retrieved records
        - use only facts contained in those records
    """
    if not query.strip():
        die("RFP text is empty")

    if top_k <= 0:
        die("--top must be greater than 0")

    if not corpus:
        return []

    print("[librarian] embedding engagement records", file=sys.stderr)

    model = load_embedding_model()

    record_embeddings = embed_engagement_records(corpus, model)
    index = build_engagement_index(record_embeddings)

    query_embedding = embed_texts(model, [query])

    k = min(top_k, len(corpus))
    scores, indices = index.search(query_embedding, k)

    matches = []
    for score, idx in zip(scores[0], indices[0]):
        record = corpus[int(idx)]
        matches.append({
            "engagement_id": record["id"],
            "score": round(float(score), 4),
            "why": explain_match(
                query_embedding,
                record,
                model,
            ),
        })

    return matches

def main():
    parser = argparse.ArgumentParser(description="RFP -> matching engagements")
    parser.add_argument("rfp", help="path to an RFP text file")
    parser.add_argument("--top", type=int, default=3)
    args = parser.parse_args()

    if args.top <= 0:
        die("--top must be greater than 0")
    try:
        query = open(args.rfp, encoding="utf-8").read()
    except FileNotFoundError:
        die(f"no such file: {args.rfp}")
    if not query.strip():
        die(f"empty RFP file: {args.rfp}")

    corpus = load_corpus()

    matches = search(query, corpus, args.top)
    capability_statement = build_capability_statement(matches, corpus)

    output = {
        "matches": matches,
        "capability_statement": capability_statement,
    }

    json.dump(
        output,
        sys.stdout,
        indent=2,
        ensure_ascii=False,
    )
    print()


if __name__ == "__main__":
    main()
