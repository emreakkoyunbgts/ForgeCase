import httpx
import logging
import sys
from fastapi import HTTPException
from circuitbreaker import circuit

from generator.exeption import VaultServiceError

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("generator_controller.log",encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])

logger=logging.getLogger(__name__)




@circuit(
    failure_threshold=3,
    recovery_timeout=30,
    expected_exception=(
            httpx.RequestError,
            VaultServiceError,)
    )
async def get_record_from_vault(record_id:str , headers:dict=None):
    async with httpx.AsyncClient(timeout=5.0) as client:
        response=await client.get(f"http://127.0.0.1:8000/engagements/{record_id}", headers=headers)
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
        elif 400<=response.status_code<500:
            logger.error(f"Error fetching record with ID {record_id} from vault: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Error fetching record with ID {record_id} from vault: {response.text}",
            )
        if response.status_code>=500:
            logger.error(f"Vault service error: {response.text}")
            raise VaultServiceError(f"Vault service error: {response.text}")

        #response.raise_for_status()
        return response.json()




@circuit(
    failure_threshold=3,
    recovery_timeout=30,
    expected_exception=(httpx.RequestError,
                        httpx.ConnectTimeout,
                        httpx.ReadTimeout,
                        httpx.ConnectError)
)
async def call_librarian_for_matching(rfp_text:str,headers:dict=None):

    url="http://localhost:8002/match"
    payload={"rfp_text": rfp_text, "top_k": 1, "strategy": "hybrid", "min_dense_score": 0.45}


    async with httpx.AsyncClient(timeout=30.0) as client:
        response=await client.post(url, json=payload, headers=headers)
        if response.status_code!=200:
            logger.error(f"Error calling librarian for matching: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Error calling librarian for matching: {response.text}",
            )
        response.raise_for_status()
        return response.json()





