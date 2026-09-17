"""Bounded structured provider calls; no credentials or model calls on import."""

import asyncio
import json
import os
from pathlib import Path
from dotenv import load_dotenv

from fastapi import HTTPException
from pydantic import ValidationError

PROVIDER_TIMEOUT_SECONDS = 60.0
MAX_PROVIDER_INPUT_CHARACTERS = 80000
load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)


async def request_structured(system, payload, schema, *, model_env, correlation_id=None):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise HTTPException(503, "Language model service is not configured")
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized) > MAX_PROVIDER_INPUT_CHARACTERS:
        raise HTTPException(422, "Content exceeds the language model input limit")
    from openai import (AsyncOpenAI, OpenAIError, APIConnectionError, APIStatusError,
                        APITimeoutError, AuthenticationError, RateLimitError)
    try:
        async with AsyncOpenAI(api_key=key, timeout=PROVIDER_TIMEOUT_SECONDS,
                               max_retries=0) as client:
            async with asyncio.timeout(PROVIDER_TIMEOUT_SECONDS):
                response = await client.responses.parse(
                    model=os.environ.get(model_env, "gpt-5.5"),
                    input=[{"role": "system", "content": system},
                           {"role": "user", "content": serialized}],
                    text_format=schema, max_output_tokens=16000,
                    extra_headers={"X-Correlation-ID": correlation_id} if correlation_id else {},
                    store=False,
                )
        if response.status != "completed" or response.output_parsed is None:
            raise HTTPException(502, "Language model returned an incomplete assessment")
        return schema.model_validate(response.output_parsed)
    except (TimeoutError, APITimeoutError):
        raise HTTPException(504, "Language model request timed out") from None
    except (AuthenticationError, APIConnectionError, RateLimitError):
        raise HTTPException(503, "Language model service is unavailable") from None
    except APIStatusError:
        raise HTTPException(502, "Language model returned an unsuccessful response") from None
    except OpenAIError:
        raise HTTPException(502, "Language model returned an invalid assessment") from None
    # A provider that answers 200 with a non-JSON body (a proxy error page, say)
    # makes the SDK hand back a str, and parsing it raises AttributeError.
    # Without these, that escapes as a bare 500 and breaks the documented
    # 'malformed dependency response is 502' contract.
    except (ValidationError, ValueError, AttributeError, TypeError):
        raise HTTPException(502, "Language model returned an invalid assessment") from None
