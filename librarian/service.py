from typing import Literal

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

from common.contract import load_corpus
from librarian.librarian import search as librarian_search
from librarian.multi_requirement import evaluate_rfp_requirements


class MatchRequest(BaseModel):
    rfp_text: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=20)
    strategy: Literal["dense", "hybrid"] = "hybrid"
    min_dense_score: float = Field(default=0.45, ge=0.0, le=1.0)


def create_app() -> FastAPI:
    app = FastAPI(
        title="CaseForge Librarian",
        version="0.1.0",
    )

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "service": "librarian",
        }

    @app.get("/search")
    def search_endpoint(
        q: str = Query(..., min_length=1),
        top: int = Query(3, ge=1, le=20),
        strategy: Literal["dense", "hybrid"] = "hybrid",
    ):
        corpus = load_corpus()

        matches = librarian_search(
            q,
            corpus,
            top_k=top,
            strategy=strategy,
        )

        return {
            "query": q,
            "strategy": strategy,
            "matches": matches,
        }

    @app.post("/match")
    def match_endpoint(body: MatchRequest):
        return evaluate_rfp_requirements(
            rfp_text=body.rfp_text,
            corpus=load_corpus(),
            top_k=body.top_k,
            strategy=body.strategy,
            min_dense_score=body.min_dense_score,
        )

    return app


app = create_app()