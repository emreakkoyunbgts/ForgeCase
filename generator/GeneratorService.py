import asyncio

import httpx
import logging
import sys
from fastapi import HTTPException
from circuitbreaker import circuit

from generator.exeption.VaultServiceError import VaultServiceError
from generator.exeption.RetryExeption import RetryException

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("generator_controller.log",encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])

logger=logging.getLogger(__name__)



MAX_RETRIES=3

BACKOFF_DELAYS = [
    0.2,
    0.5,
    1.0
]

RETRYABLE_STATUS_CODES = {
    500,
    502,
    503,
    504,
}





@circuit(
    failure_threshold=3,
    recovery_timeout=30,
    expected_exception=(
            httpx.RequestError,
            VaultServiceError,
            RetryException)
    )
async def get_record_from_vault(record_id:str , headers:dict=None):
    print("VaultServiceError =", VaultServiceError)
    print("VaultServiceError type =", type(VaultServiceError))
    print("RetryException =", RetryException)
    print("RetryException type =", type(RetryException))
    print("RequestError =", httpx.RequestError)
    print("RequestError type =", type(httpx.RequestError))

    for attemt in range(MAX_RETRIES):
        try:

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

                    if attemt < MAX_RETRIES - 1:
                        await asyncio.sleep(BACKOFF_DELAYS[attemt])
                        logger.info(f"Retrying vault in {BACKOFF_DELAYS[attemt]} seconds...")
                        continue
                    else:
                        logger.error(f"Max retries exceeded for calling vault service.")
                        raise RetryException(depency="vault", message=f"Max retries exceeded for calling vault service: {response.text}")
                    raise VaultServiceError(f"Vault service error: {response.text}")

                #response.raise_for_status()
                return response.json()
        except (httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.RequestError) as e:
            logger.warning(f"Attempt {attemt + 1} failed. Retrying...")
            if attemt < MAX_RETRIES - 1:
                logger.info(f"Retrying vault in {BACKOFF_DELAYS[attemt]} seconds...")
                await asyncio.sleep(BACKOFF_DELAYS[attemt])

            else:
                logger.error(f"Max retries exceeded for calling vault service.")
                raise RetryException(depency="vault", message=f"Max retries exceeded for calling vault service: {e}")




@circuit(
    failure_threshold=3,
    recovery_timeout=30,
    expected_exception=(httpx.RequestError,
                        httpx.ConnectTimeout,
                        httpx.ReadTimeout,
                        httpx.ConnectError,
                        RetryException)
)
async def call_librarian_for_matching(rfp_text:str,headers:dict=None):

    url="http://localhost:8002/match"
    payload={"rfp_text": rfp_text, "top_k": 1, "strategy": "hybrid", "min_dense_score": 0.45}



    for attempt in range(MAX_RETRIES):

        try:

            async with httpx.AsyncClient(timeout=30.0) as client:
                response=await client.post(url, json=payload, headers=headers)

                if response.is_success:
                    logger.info(f"Successfully called librarian for matching: {response.json()}")
                    return response.json()

                if response.status_code not in RETRYABLE_STATUS_CODES:
                    logger.error(f" (not retryable) Error calling librarian for matching: {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Error calling librarian for matching: {response.text}",
                    )

                logger.warning(f"Attempt {attempt + 1} failed with status code {response.status_code}. Retrying...")
                if attempt < MAX_RETRIES - 1:
                    logger.info(f"Retrying librarian in {BACKOFF_DELAYS[attempt]} seconds...")
                    await asyncio.sleep(BACKOFF_DELAYS[attempt])
                    continue


                raise RetryException(depency="librarian", message=f"Max retries exceeded for calling librarian for matching: {response.text}")
                #response.raise_for_status()


        except (httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.RequestError) as e:

                logger.warning(f"Attempt {attempt + 1} failed. Retrying...")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(BACKOFF_DELAYS[attempt])
                    logger.info(f"Retrying librarian in {BACKOFF_DELAYS[attempt]} seconds...")
                else:
                    logger.error(f"Max retries exceeded for calling librarian for matching.")
                    raise RetryException(depency="librarian", message=f"Max retries exceeded for calling librarian for matching: {e}")






