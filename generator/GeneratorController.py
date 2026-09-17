"""Generate single-source EN/DE/TR drafts from authoritative Vault records."""
import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from common.drafts import Language, validate_record_id
from common.services import install_http_middleware, request_headers
from generator.GeneratorService import get_record_from_vault, get_vault_client, call_librarian_for_matching
from generator.core import generate_mcs
from generator.translation import get_translator

app = FastAPI(title="CaseForge Generator", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    expose_headers=["X-Correlation-ID"],
)
install_http_middleware(app)


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: str = Field(min_length=1, max_length=200)
    language: Language = "en"
    _record_id = field_validator("record_id")(validate_record_id)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse(status_code=422, content={"detail": [
        {key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()
    ]})


@app.get("/health")
def health():
    return {"status": "ok", "service": "generator", "languages": ["en", "de", "tr"]}


async def generate_for(payload, request, client, translator):
    record = await get_record_from_vault(
        payload.record_id, client, request.state.correlation_id,
        request.headers.get("Authorization"),
    )
    draft = generate_mcs(record)
    # A model translates all requested languages: an English source is not assumed.
    return await translator(draft, record, payload.language, request.state.correlation_id)


@app.post("/generate")
async def generate(payload: GenerateRequest, request: Request,
                   client: httpx.AsyncClient = Depends(get_vault_client),
                   translator=Depends(get_translator)):
    return await generate_for(payload, request, client, translator)


async def legacy(record, language, request, client, translator):
    try:
        payload = GenerateRequest(record_id=record.get("id"), language=language)
    except (ValueError, AttributeError):
        raise HTTPException(422, "A valid record.id is required") from None
    return await generate_for(payload, request, client, translator)


@app.post("/generator/mcs/eng", deprecated=True)
@app.post("/generator/mcs", deprecated=True)
async def legacy_en(record: dict, request: Request,
                    client=Depends(get_vault_client), translator=Depends(get_translator)):
    return await legacy(record, "en", request, client, translator)


@app.post("/generator/mcs/german", deprecated=True)
async def legacy_de(record: dict, request: Request,
                    client=Depends(get_vault_client), translator=Depends(get_translator)):
    return await legacy(record, "de", request, client, translator)


@app.post("/generator/mcs/turkish", deprecated=True)
async def legacy_tr(record: dict, request: Request,
                    client=Depends(get_vault_client), translator=Depends(get_translator)):
    return await legacy(record, "tr", request, client, translator)


@app.post("/generator/mcs/query", deprecated=True)
async def query_generate(query: str, request: Request, language: Language = "en",
                         client=Depends(get_vault_client), translator=Depends(get_translator)):
    if not query.strip():
        raise HTTPException(422, "Query must contain text")
    record_id = await call_librarian_for_matching(query, request_headers(), client)
    return await generate_for(GenerateRequest(record_id=record_id, language=language),
                              request, client, translator)

