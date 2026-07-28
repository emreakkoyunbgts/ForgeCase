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

    matches = search(query, load_corpus(), args.top)
    json.dump({"matches": matches}, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
