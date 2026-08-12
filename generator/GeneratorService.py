import httpx
import logging
import sys
from fastapi import HTTPException

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("generator_controller.log",encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])

logger=logging.getLogger(__name__)

async def get_record_from_vault(record_id:str):
    try:
        async with httpx.AsyncClient() as client:
            response=await client.get(f"https://127.0.0.1/8080/engagements/{record_id}")
            if response.status_code==404:
                logger.error(f"Record with ID {record_id} not found in vault")
                raise HTTPException(status_code=404,
                                    detail=f"Record with ID {record_id} not found in vault")
            elif response.status_code==422:
                logger.error(f"as_of must be a valid ISO-8601 datetime: {record_id}")
                raise HTTPException(
                    status_code=422,
                    detail="as_of must be a valid ISO-8601 datetime",
                )
            elif response.status_code!=200:
                logger.error(f"Error fetching record with ID {record_id} from vault: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Error fetching record with ID {record_id} from vault: {response.text}",
                )

            response.raise_for_status()
            return response.json()

    except httpx.RequestError as e:
        logger.error(f"An error occurred while requesting record with ID {record_id} from vault: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"An error occurred while requesting record with ID {record_id} from vault: {e}",
        )

