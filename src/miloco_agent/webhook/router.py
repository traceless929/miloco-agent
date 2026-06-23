"""Miloco-compatible webhook JSON envelope."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from miloco_agent.config import MilocoAgentSettings, load_settings
from miloco_agent.webhook.handlers import handle_agent, handle_get_trace

T = TypeVar("T")


class WebhookResponse(BaseModel, Generic[T]):
    code: int
    message: str
    data: T | None = None


class WebhookBody(BaseModel):
    action: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


def ok(data: Any = None) -> dict[str, Any]:
    return {"code": 0, "message": "ok", "data": data}


def fail(code: int, message: str) -> dict[str, Any]:
    return {"code": code, "message": message, "data": None}


_ACTIONS = {
    "agent": handle_agent,
    "get_trace": handle_get_trace,
}


def get_settings() -> MilocoAgentSettings:
    return load_settings()


async def verify_bearer(
    request: Request,
    settings: MilocoAgentSettings = Depends(get_settings),
) -> None:
    expected = settings.agent.auth_bearer
    if not expected:
        return
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized")


router = APIRouter()


@router.post("/miloco/webhook")
async def miloco_webhook(
    body: WebhookBody,
    _: None = Depends(verify_bearer),
) -> JSONResponse:
    handler = _ACTIONS.get(body.action)
    if handler is None:
        return JSONResponse(
            status_code=404,
            content=fail(2001, f"Action '{body.action}' not found"),
        )
    try:
        result = await handler(body.payload)
        return JSONResponse(status_code=200, content=ok(result))
    except ValueError as exc:
        return JSONResponse(status_code=400, content=fail(1001, str(exc)))
    except Exception as exc:  # noqa: BLE001 — mirror plugin 500 envelope
        return JSONResponse(status_code=500, content=fail(3000, str(exc)))
