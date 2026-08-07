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

def tokenize(text):
    """
    Convert text into normalized terms for BM25 keyword retrieval.
    """
    return [
        token.casefold()
        for token in TOKEN_PATTERN.findall(text)
    ]


def bm25_scores(query, corpus, k1=1.5, b=0.75):
    """
    Calculate one BM25 keyword-relevance score per engagement.

    BM25 rewards records containing important query terms while accounting
    for document length and how rare each term is across the corpus.
    """
    documents = [
        tokenize(searchable_text(record))
        for record in corpus
    ]

    document_count = len(documents)

    if document_count == 0:
        return np.array([], dtype="float32")

    average_document_length = (
        sum(len(document) for document in documents)
        / document_count
    )

    if average_document_length == 0:
        average_document_length = 1.0

    document_frequencies = Counter()

    for document in documents:
        document_frequencies.update(set(document))

    query_terms = set(tokenize(query))

    scores = np.zeros(
        document_count,
        dtype="float32",
    )

    for document_index, document in enumerate(documents):
        term_frequencies = Counter(document)
        document_length = len(document)

        for term in query_terms:
            frequency = term_frequencies.get(term, 0)

            if frequency == 0:
                continue

            documents_with_term = document_frequencies[term]

            inverse_document_frequency = math.log(
                1
                + (
                    document_count
                    - documents_with_term
                    + 0.5
                )
                / (
                    documents_with_term
                    + 0.5
                )
            )

            length_normalization = (
                1
                - b
                + b
                * document_length
                / average_document_length
            )

            denominator = (
                frequency
                + k1 * length_normalization
            )

            scores[document_index] += (
                inverse_document_frequency
                * frequency
                * (k1 + 1)
                / denominator
            )

    return scores


def normalize_scores(scores):
    """
    Scale an array of scores to the range 0–1.

    Dense cosine similarity and BM25 use different numerical scales, so
    normalization is required before combining them.
    """
    scores = np.asarray(
        scores,
        dtype="float32",
    )

    if scores.size == 0:
        return scores

    minimum = float(scores.min())
    maximum = float(scores.max())

    if maximum - minimum < 1e-8:
        return np.zeros_like(scores)

    return (
        scores - minimum
    ) / (
        maximum - minimum
    )


def all_dense_scores(
    index,
    query_embedding,
    corpus_size,
):
    """
    Return the FAISS dense score for every record in corpus order.
    """
    scores, indices = index.search(
        query_embedding,
        corpus_size,
    )

    ordered_scores = np.zeros(
        corpus_size,
        dtype="float32",
    )

    for score, index_position in zip(
        scores[0],
        indices[0],
    ):
        ordered_scores[int(index_position)] = float(score)

    return ordered_scores


def rerank_candidates(
    dense_scores,
    keyword_scores,
    top_k,
    dense_weight=0.65,
):
    """
    Combine dense and BM25 candidates and rerank them.

    The initial weight gives semantic retrieval 65% of the final score and
    keyword retrieval 35%. These values are starting parameters and should
    later be evaluated against labelled queries.
    """
    if not 0.0 <= dense_weight <= 1.0:
        die("dense_weight must be between 0 and 1")

    corpus_size = len(dense_scores)

    if corpus_size == 0:
        return [], np.array([], dtype="float32")

    candidate_count = min(
        corpus_size,
        max(top_k * 3, 6),
    )

    dense_candidates = np.argsort(
        dense_scores
    )[::-1][:candidate_count]

    keyword_candidates = np.argsort(
        keyword_scores
    )[::-1][:candidate_count]

    # dict.fromkeys removes duplicates while preserving order.
    candidate_indices = list(
        dict.fromkeys([
            *map(int, dense_candidates),
            *map(int, keyword_candidates),
        ])
    )

    normalized_dense = normalize_scores(
        dense_scores
    )

    normalized_keyword = normalize_scores(
        keyword_scores
    )

    keyword_weight = 1.0 - dense_weight

    combined_scores = (
        dense_weight * normalized_dense
        + keyword_weight * normalized_keyword
    )

    ranked_indices = sorted(
        candidate_indices,
        key=lambda index: (
            float(combined_scores[index]),
            float(dense_scores[index]),
        ),
        reverse=True,
    )

    return (
        ranked_indices[:top_k],
        combined_scores,
    )

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

def search(
    query,
    corpus,
    top_k=3,
    strategy="hybrid",
    dense_weight=0.65,
):
    """
    Return the top_k engagements most relevant to the query.

    L1:
        - embed each engagement record
        - embed the RFP query
        - use FAISS for dense semantic retrieval

    L2:
        - explain each result using structured fields from the record

    L3:
        - build a grounded capability statement from the retrieved records
        - use only facts contained in those records

    CF-71:
        - calculate BM25 keyword-relevance scores
        - combine dense and keyword candidates
        - rerank candidates using both retrieval signals

    strategy="dense" preserves the original dense-only baseline.
    strategy="hybrid" uses dense retrieval plus BM25 reranking.
    """
    if not query.strip():
        die("RFP text is empty")

    if top_k <= 0:
        die("--top must be greater than 0")

    if strategy not in {"dense", "hybrid"}:
        die("strategy must be 'dense' or 'hybrid'")

    if not 0.0 <= dense_weight <= 1.0:
        die("dense_weight must be between 0 and 1")

    if not corpus:
        return []

    print(
        "[librarian] embedding engagement records",
        file=sys.stderr,
    )

    model = load_embedding_model()

    record_embeddings = embed_engagement_records(
        corpus,
        model,
    )

    index = build_engagement_index(
        record_embeddings
    )

    query_embedding = embed_texts(
        model,
        [query],
    )

    k = min(
        top_k,
        len(corpus),
    )

    dense_scores = all_dense_scores(
        index,
        query_embedding,
        len(corpus),
    )

    if strategy == "dense":
        ranked_indices = list(
            map(
                int,
                np.argsort(dense_scores)[::-1][:k],
            )
        )

        final_scores = dense_scores

    else:
        keyword_scores = bm25_scores(
            query,
            corpus,
        )

        ranked_indices, final_scores = rerank_candidates(
            dense_scores,
            keyword_scores,
            top_k=k,
            dense_weight=dense_weight,
        )

    matches = []

    for index_position in ranked_indices:
        record = corpus[int(index_position)]

        matches.append({
            "engagement_id": record["id"],
            "score": round(
                float(final_scores[index_position]),
                4,
            ),
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
    parser.add_argument("--strategy", choices=["dense", "hybrid"], default="hybrid",help=(
        "retrieval strategy: dense baseline "
        "or dense + BM25 hybrid"
        ),
    )
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

    matches = search(query, corpus, top_k=args.top, strategy=args.strategy)
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
