"""Generator HTTP dependencies; no local record or model-index fallback."""
import os
import httpx
from fastapi import HTTPException
from common.source import get_record_from_vault, get_vault_client


async def call_librarian_for_matching(query, headers=None, client=None):
    url = os.getenv("LIBRARIAN_URL", "http://127.0.0.1:8002").rstrip("/")
    async def send(connection):
        try:
            response = await connection.post(
                url + "/match", json={"rfp_text": query, "top_k": 1},
                headers=headers, timeout=20, follow_redirects=False)
        except httpx.TimeoutException:
            raise HTTPException(504, "Librarian request timed out") from None
        except httpx.RequestError:
            raise HTTPException(503, "Librarian is unavailable") from None
        if response.status_code in {401, 403}:
            raise HTTPException(response.status_code, "Librarian denied access")
        if response.status_code != 200:
            raise HTTPException(502, "Librarian returned an unsuccessful response")
        try:
            data = response.json()
            requirements = data["requirements"]
            if not isinstance(requirements, list):
                raise ValueError()
            for requirement in requirements:
                best = requirement.get("best_match")
                if best and isinstance(best.get("engagement_id"), str):
                    return best["engagement_id"]
        except (ValueError, TypeError, KeyError, AttributeError):
            raise HTTPException(502, "Librarian returned an invalid match response") from None
        raise HTTPException(404, "No matching engagement was found")
    if client is not None:
        return await send(client)
    async with httpx.AsyncClient() as connection:
        return await send(connection)



