import sys

from fastapi import FastAPI, HTTPException
import logging

from common.contract import load_seed
from generator.generator import generate_multi_source

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("generator_controller.log",encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])

logger=logging.getLogger(__name__)
app=FastAPI()


@app.get("/mcs/{id}")
async def get_mcs(id: str):
    """
    Get the multi-source content for a given record ID.
    """
    if id is None:
        logger.error("Record ID is None")
        raise HTTPException(status_code=400, detail="Record ID is required")

    # There is stub for now , we will implement the actual logic when finished with vault api
    try:
        record = load_seed(id)
    except Exception as e:
        logger.error(f"Error loading seed record for ID {id}: {e}")
        raise HTTPException(status_code=404, detail=f"Record with ID {id} not found")

    mcs=generate_multi_source([record])

    return mcs






