import uuid

from fastapi import FastAPI, HTTPException , Request ,Response
import logging
import sys

from verifier.verifier import verify

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("verifier_controller.log",encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])

logger=logging.getLogger(__name__)
from generator.GeneratorService import get_record_from_vault

app=FastAPI()

@app.post("/verify/{id}")
async def verify_record_id(record: dict , mcs: dict , request: Request , response: Response):

    if id is None:
        logger.error("Record ID is None")
        raise HTTPException(status_code=400, detail="Record ID is required")
    if dict is None:
        logger.error("MCS is None")
        raise HTTPException(status_code=400, detail="MCS is required")


    correlation_id = request.headers.get("X-Correlation-ID", None)

    if correlation_id is None:
        logger.warning(f"Correlation ID: {correlation_id}")
        correlation_id = str(uuid.uuid4())
        logger.info(f"Generated new Correlation ID: {correlation_id}")

    authorization=request.headers.get("Authorization", None)

    headers={"X-Correlation-ID": correlation_id,}

    if authorization:
        headers["Authorization"]=authorization
    else:
        logger.warning("Authorization header is missing")



    """
    try:
        record = await get_record_from_vault(record_id,headers=headers)
    except Exception as e:
        logger.error(f"Error loading seed record for ID {record_id}: {e}")
        raise HTTPException(status_code=404, detail=f"Record with ID {id} not found")
        
    """

    response_verifier=verify(mcs,record)
    logger.info(f"Verification completed for record ID {record["id"]} with verdict: {response_verifier['verdict']}")
    response.headers["X-Correlation-ID"]=correlation_id
    return response_verifier

@app.get("/health")
async def health_check():
    """
    Health check endpoint to verify that the service is running.
    """
    return {"status": "ok"}

