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
            "why": "TODO(Arda): explain what actually matched",
        })

    return matches
    
    # ----------------------------------------------------------------------


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
