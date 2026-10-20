"""Optional, loopback-only read-only HTTP API for Shnifter agents.

Run with: uvicorn shnifter_agent_api:app --host 127.0.0.1 --port 8766
Never expose unauthenticated endpoints to the public Internet.
"""
from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict

from shnifter_actions import invoke_action

app = FastAPI(title="Shnifter Research API", version="0.1.0",
              description="Read-only research operations. No brokerage/order routes.")


class ActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    params: dict[str, Any] = Field(default_factory=dict)


def read_only_access(request: Request, x_api_key: str | None = Header(default=None)):
    expected = os.environ.get("SHNIFTER_READONLY_API_KEY")
    if expected:
        if not x_api_key or not hmac.compare_digest(expected, x_api_key):
            raise HTTPException(status_code=401, detail="invalid API key")
    else:
        remote = request.client.host if request.client else ""
        if remote not in ("127.0.0.1", "::1"):
            raise HTTPException(status_code=403, detail="API key required outside loopback")


@app.get("/v1/actions", dependencies=[Depends(read_only_access)])
def actions():
    return invoke_action("actions.list")


@app.post("/v1/actions/{action_name}", dependencies=[Depends(read_only_access)])
def run_action(action_name: str, payload: ActionPayload, request: Request):
    if len(str(payload.params)) > 500_000:
        raise HTTPException(status_code=413, detail="payload too large")
    try:
        return invoke_action(action_name, payload.params)
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
