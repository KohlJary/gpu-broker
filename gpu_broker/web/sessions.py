"""Interactive-session routes: borrow the GPU for ComfyUI or a service, and give it back.

The main token and client keys may both use these. A client key's session is its own: its
name is the requester (whatever the body claims), it can read only sessions it opened, and it
can end only the session it holds. The main token sees and ends any session, as before.
"""
from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..broker import Broker
from ..constants import SESSION_KEY, ModelStatus, Runner
from ..sessions import IDLE_MINUTES_KEY
from .jobs import CLIENT_ID_STATE, requester

DEFAULT_REQUESTER = "dashboard"
SESSION_RUNNERS = frozenset({Runner.COMFY, Runner.SERVICE})   # what a session can borrow the card for
NOT_YOURS = "that session belongs to another caller"
NO_SESSION = "no such session"


def router(broker: Broker) -> APIRouter:
    r = APIRouter()

    def mine(request: Request, jid: str) -> bool:
        """May this caller act on session job `jid`? The main token may; a client key only on its own."""
        kid = getattr(request.state, CLIENT_ID_STATE, None)
        j = broker.store.job(jid)
        return j is not None and (kid is None or j.get("owner") == kid)

    @r.post("/v1/sessions")
    def start(body: dict[str, Any], request: Request) -> dict[str, Any]:
        key = body.get("model")
        m = broker.catalog.models.get(key) if isinstance(key, str) else None
        if m is None or m.get("runner") not in SESSION_RUNNERS or m.get("status") != ModelStatus.READY:
            raise HTTPException(HTTPStatus.BAD_REQUEST, f"{key!r} is not a ready ComfyUI model or service")
        idle = body.get(IDLE_MINUTES_KEY, 0)
        if not isinstance(idle, (int, float)) or idle < 0:
            raise HTTPException(HTTPStatus.BAD_REQUEST, f"`{IDLE_MINUTES_KEY}` must be a non-negative number")
        jid, info = broker.submit({"model": key, SESSION_KEY: True, IDLE_MINUTES_KEY: idle},
                                  requester(request, str(body.get("requester") or DEFAULT_REQUESTER)),
                                  owner=getattr(request.state, CLIENT_ID_STATE, None))
        return {"id": jid, **info, "comfy_template": m.get("comfy_template"), "open_url": m.get("open_url")}

    @r.get("/v1/sessions/{jid}")
    def one(jid: str, request: Request) -> dict[str, Any]:
        """A session's job, and whether it holds the card now: what a client key polls, since
        /v1/status (every caller's work) is the main token's."""
        if not mine(request, jid):
            raise HTTPException(HTTPStatus.NOT_FOUND, NO_SESSION)   # someone else's reads as absent
        j = broker.view(jid) or {}
        active = broker.sessions.view()
        return {"job": j, "live": bool(active and active["job"] == jid)}

    @r.post("/v1/sessions/end")
    def end(request: Request, body: dict[str, Any] | None = None) -> dict[str, bool]:
        active = broker.sessions.view()
        if getattr(request.state, CLIENT_ID_STATE, None) is not None:
            if active is None:
                return {"ended": False}
            if not mine(request, active["job"]) or (body and body.get("id") not in (None, active["job"])):
                raise HTTPException(HTTPStatus.FORBIDDEN, NOT_YOURS)
        elif body and body.get("id") and (active is None or active["job"] != body["id"]):
            return {"ended": False}   # the main token named a session that no longer holds the card
        return {"ended": broker.sessions.end()}

    return r
