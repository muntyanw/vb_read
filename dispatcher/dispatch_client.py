# viber_worker/dispatch_client.py
import os
from typing import Optional, Dict, Any
import asyncio
import httpx
from pydantic import BaseModel
from datetime import datetime, timezone

DISPATCH_URL = os.getenv("DISPATCH_URL", "http://192.168.1.223:8888/api/v1/dispatch/analyze")
DISPATCH_API_KEY = os.getenv("DISPATCH_API_KEY", "66fBbZsL72")

class DispatchError(Exception):
    pass

class DispatchResult(BaseModel):
    message_id: str
    extracted: Dict[str, Any]
    decision: Dict[str, Any]
    actions: list

async def send_for_analysis(
    *,
    message_id: str,
    text: str,
    chat_id: Optional[str] = None,
    sender: Optional[str] = None,
    attachments: Optional[list] = None,
    locale: str = "uk",
    timeout_s: float = 8.0,
    retries: int = 2,
) -> DispatchResult:
    payload = {
        "message_id": message_id,
        "chat_id": chat_id,
        "sender": sender,
        "text": text,
        "attachments": attachments or [],
        "received_at": datetime.now(timezone.utc).isoformat(),
        "locale": locale,
    }

    headers = {"X-API-Key": DISPATCH_API_KEY}

    last_exc = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(DISPATCH_URL, json=payload, headers=headers)
                if resp.status_code == 401:
                    raise DispatchError("Unauthorized: check X-API-Key")
                resp.raise_for_status()
                data = resp.json()
                return DispatchResult(**data)
        except Exception as e:
            last_exc = e
            if attempt < retries:
                await asyncio.sleep(0.5 * (attempt + 1))  # backoff
            else:
                raise DispatchError(f"Dispatch request failed after {retries+1} tries: {e}") from e
    # theoretically unreachable
    raise DispatchError(f"Dispatch failed: {last_exc}")
