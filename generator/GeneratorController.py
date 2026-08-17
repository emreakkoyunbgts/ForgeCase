import sys
import uuid

from fastapi import FastAPI, HTTPException , Response , Request
import logging

from common.contract import load_seed
from generator.GeneratorService import get_record_from_vault
from generator.generator import generate_multi_source, get_five_sections_with_llm, get_llm_output_german, \
    get_llm_output_turkish

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("generator_controller.log",encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])

logger=logging.getLogger(__name__)
app=FastAPI()


@app.post("generator/mcs/eng")
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

