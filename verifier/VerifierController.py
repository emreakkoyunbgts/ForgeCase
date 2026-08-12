from fastapi import FastAPI, HTTPException
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
async def verify_record_id(record_id: str , mcs: dict):
    if id is None:
        logger.error("Record ID is None")
        raise HTTPException(status_code=400, detail="Record ID is required")
    if dict is None:
        logger.error("MCS is None")
        raise HTTPException(status_code=400, detail="MCS is required")

    try:
        record = await get_record_from_vault(record_id)
    except Exception as e:
        logger.error(f"Error loading seed record for ID {record_id}: {e}")
        raise HTTPException(status_code=404, detail=f"Record with ID {id} not found")

    response=verify(mcs,record)
    logger.info(f"Verification completed for record ID {record_id} with verdict: {response['verdict']}")
    return response

@app.get("/health")
async def health_check():
    """
    Health check endpoint to verify that the service is running.
    """
    return {"status": "ok"}

