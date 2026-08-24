import sys
import uuid

import httpx
from circuitbreaker import CircuitBreakerError

from fastapi import FastAPI, HTTPException , Response , Request
from fastapi.middleware.cors import CORSMiddleware
import logging


from common.contract import load_seed, load_corpus
from generator.GeneratorService import get_record_from_vault, call_librarian_for_matching
from generator.exeption.VaultServiceError import VaulServiceError
from generator.generator import generate_multi_source, get_five_sections_with_llm, get_llm_output_german, \
    get_llm_output_turkish

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("generator_controller.log",encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])

logger=logging.getLogger(__name__)
app=FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173",],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.post("/generator/mcs/eng")
async def get_mcs(record: dict, request: Request , response: Response):
    """
    Get the multi-source content for a given record ID.
    """
    if id is None:
        logger.error("Record ID is None")
        raise HTTPException(status_code=400, detail="Record ID is required")


    correlation_id=request.headers.get("X-Correlation-ID", None)
    if correlation_id is None:
        logger.warning(f"Correlation ID: {correlation_id}")
        correlation_id=str(uuid.uuid4())
        logger.info(f"Generated new Correlation ID: {correlation_id}")

    authorization=request.headers.get("Authorization", None)
    headers={"X-Correlation-ID": correlation_id,}

    if authorization:
        headers["Authorization"]=authorization
    else:
        logger.warning("Authorization header is missing")

    """
    try:
        record =await get_record_from_vault(id, headers=headers)
    except Exception as e:
        logger.error(f"Error loading seed record for ID {id}: {e}")
        raise HTTPException(status_code=404, detail=f"Record with ID {id} not found")
        
    """

    mcs=generate_multi_source([record])

    response.headers["X-Correlation-ID"]=correlation_id


    return mcs



@app.post("/generator/mcs/german")
async def create_german_translation(record: dict , request: Request , response: Response):
    """
    Create a German translation for a given record.
    """

    correlation_id=request.headers.get("X-Correlation-ID", None)
    if correlation_id is None:
        logger.warning(f"Correlation ID: {correlation_id}")
        correlation_id=str(uuid.uuid4())
        logger.info(f"Generated new Correlation ID: {correlation_id}")

    headers={"X-Correlation-ID": correlation_id,}

    authorization=request.headers.get("Authorization", None)
    if authorization:
        headers["Authorization"]=authorization
    else:
        logger.warning("Authorization header is missing")




    if record is None:
        logger.error("Record is None")
        raise HTTPException(status_code=400, detail="Record is required")


    mcs=generate_multi_source([record])
    llm_output_ge = get_llm_output_german(mcs)

    response.headers["X-Correlation-ID"]=correlation_id

    return llm_output_ge


@app.post("/generator/mcs/turkish")
async def create_turkish_translation(record: dict, request: Request, response: Response):
    """
    Create a German translation for a given record.
    """

    correlation_id = request.headers.get("X-Correlation-ID", None)
    if correlation_id is None:
        logger.warning(f"Correlation ID: {correlation_id}")
        correlation_id = str(uuid.uuid4())
        logger.info(f"Generated new Correlation ID: {correlation_id}")

    headers = {"X-Correlation-ID": correlation_id, }

    authorization = request.headers.get("Authorization", None)
    if authorization:
        headers["Authorization"] = authorization
    else:
        logger.warning("Authorization header is missing")

    if record is None:
        logger.error("Record is None")
        raise HTTPException(status_code=400, detail="Record is required")

    mcs = generate_multi_source([record])
    llm_output_tr = get_llm_output_turkish(mcs)

    response.headers["X-Correlation-ID"] = correlation_id

    return llm_output_tr



@app.post("/generator/mcs/query")
async def create_mcs_with_query(query: str , request: Request , response: Response):
    """
    Create a multi-source content for a given query.
    """
    if query is None:
        logger.error("Query is None")
        raise HTTPException(status_code=400, detail="Query is required")

    correlation_id = request.headers.get("X-Correlation-ID", None)
    if correlation_id is None:
        logger.warning(f"Correlation ID: {correlation_id}")
        correlation_id = str(uuid.uuid4())
        logger.info(f"Generated new Correlation ID: {correlation_id}")

    headers = {"X-Correlation-ID": correlation_id, }

    authorization = request.headers.get("Authorization", None)
    if authorization:
        headers["Authorization"] = authorization
    else:
        logger.warning("Authorization header is missing")

    try:
        # Implement the logic when api is exposed
        #librerian_response = evaluate_rfp_requirements(query ,load_corpus(), top_k=1)
        librerian_response = await call_librarian_for_matching(query, headers=headers)
    except CircuitBreakerError as e:
        logger.error(f"Circuit breaker error while calling librarian for matching: {e}")
        raise HTTPException(status_code=503,
                            detail=f"Circuit breaker error while calling librarian for matching: {e}")
    except httpx.TimeoutException as e:
        logger.error(f"Timeout error while calling librarian for matching: {e}")
        raise HTTPException(status_code=504,
                            detail=f"Timeout error while calling librarian for matching: {e}")
    except httpx.ConnectError as e:
        logger.error(f"Connection error while calling librarian for matching: {e}")
        raise HTTPException(status_code=503,
                            detail=f"Connection error while calling librarian for matching: {e}")
    except httpx.HTTPStatusError as e:
        status_code=e.response.status_code
        logger.error(f"HTTP status error while calling librarian for matching: {e}")

        if 400<= status_code<500:
            raise HTTPException(status_code=status_code,
                                detail=f"Client error while calling librarian for matching: {e}")

        raise HTTPException(status_code=503,
                            detail=f"Server error while calling librarian for matching: {e}")


    logger.info(f"Succesfully loaded respose : {librerian_response}")
    record_id = librerian_response["requirements"][0]["best_match"]["engagement_id"]

    try:
        record = await get_record_from_vault(record_id, headers=headers)
        logger.info(f"Successfully loaded seed record for ID {record_id}")
    except CircuitBreakerError as e:
        logger.error(f"Circuit breaker error while loading seed record for ID {record_id}: {e}")
        raise HTTPException(status_code=503,
                            detail=f"Circuit breaker error while loading seed record for ID {record_id}: {e}")
    except httpx.TimeoutException as e:
        logger.error(f"Timeout error while loading seed record for ID {record_id}: {e}")
        raise HTTPException(status_code=504,
                            detail=f"Timeout error while loading seed record for ID {record_id}: {e}")
    except httpx.ConnectError as e:
        logger.error(f"Connection error while loading seed record for ID {record_id}: {e}")
        raise HTTPException(status_code=503,
                            detail=f"Connection error while loading seed record for ID {record_id}: {e}")
    except VaulServiceError as e:
        logger.error(f"Vault service error while loading seed record for ID {record_id}: {e}")
        raise HTTPException(status_code=503,
                            detail=f"Vault service error while loading seed record for ID {record_id}: {e}")
    mcs = generate_multi_source([record])

    response.headers["X-Correlation-ID"] = correlation_id

    return mcs




async def get_llm_output_from_record_id(id: str):
    """
    Get the LLM output for a given record ID.
    """
    if id is None:
        logger.error("Record ID is None")
        raise HTTPException(status_code=400, detail="Record ID is required")

    try:
        record = load_seed(id)
    except Exception as e:
        logger.error(f"Error loading seed record for ID {id}: {e}")
        raise HTTPException(status_code=404, detail=f"Record with ID {id} not found")

    mcs=generate_multi_source([record])
    llm_output = get_five_sections_with_llm(mcs)

    return llm_output

async def get_llm_output(mcs:dict):
    """
    Get the LLM output for a given multi-source content.
    """
    if mcs is None:
        logger.error("Multi-source content is None")
        raise HTTPException(status_code=400, detail="Multi-source content is required")

    llm_output = get_five_sections_with_llm(mcs)
    return llm_output



@app.get("/health")
async def health_check():
    """
    Health check endpoint to verify that the service is running.
    """
    return {"status": "ok"}

