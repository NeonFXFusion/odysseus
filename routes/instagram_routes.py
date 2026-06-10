"""FastAPI routes for the built-in Instagram DM panel."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.auth_helpers import require_user
from src.instagram_tags import attach_instagram_tags, get_instagram_tag_rows


class InstagramSendRequest(BaseModel):
    account: str | None = None
    thread_id: str | None = None
    username: str | None = None
    user_id: str | None = None
    text: str = ""
    attachments: list[Any] | None = None


def _provider(account=None):
    from mcp_servers.instagram_server import InstagramPrivateProvider
    return InstagramPrivateProvider(account=account)


def _account_rows():
    from mcp_servers.instagram_server import _load_accounts_raw, _public_account
    return [_public_account(row) for row in _load_accounts_raw()]


def setup_instagram_routes() -> APIRouter:
    router = APIRouter(prefix="/api/instagram", tags=["instagram"])

    @router.get("/accounts")
    async def list_accounts(request: Request):
        require_user(request)
        rows = await asyncio.to_thread(_account_rows)
        return {"accounts": rows}

    @router.get("/threads")
    async def list_threads(request: Request, account: str | None = None, max_results: int = 30):
        owner = require_user(request)
        try:
            provider = _provider(account)
            threads = await asyncio.to_thread(provider.list_threads, max_results)
            account_id = str(provider.account.get("id") or account or "")
            threads = [
                attach_instagram_tags(thread, owner=owner or "", account_id=account_id)
                for thread in threads
            ]
            return {
                "account": provider.account_label(),
                "account_id": account_id,
                "threads": threads,
            }
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/threads/{thread_id}")
    async def read_thread(
        thread_id: str,
        request: Request,
        account: str | None = None,
        max_messages: int = 50,
    ):
        owner = require_user(request)
        try:
            provider = _provider(account)
            thread = await asyncio.to_thread(provider.read_thread, thread_id, max_messages)
            account_id = str(provider.account.get("id") or account or "")
            thread = attach_instagram_tags(thread, owner=owner or "", account_id=account_id)
            return {
                "account": provider.account_label(),
                "account_id": account_id,
                "thread": thread,
            }
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/search")
    async def search_messages(
        request: Request,
        q: str = "",
        account: str | None = None,
        max_threads: int = 30,
        max_messages_per_thread: int = 30,
    ):
        owner = require_user(request)
        query = (q or "").strip()
        if not query:
            return {"messages": [], "total": 0, "query": query}
        try:
            provider = _provider(account)
            messages = await asyncio.to_thread(
                provider.search_messages,
                query,
                max_threads,
                max_messages_per_thread,
            )
            account_id = str(provider.account.get("id") or account or "")
            tag_rows = get_instagram_tag_rows(owner=owner or "", account_id=account_id)
            by_message = {str(row.get("message_id") or ""): row for row in tag_rows}
            for msg in messages:
                row = by_message.get(str(msg.get("message_id") or ""))
                if row:
                    msg["tags"] = row.get("tags") or []
                    msg["triage_score"] = row.get("score", 0)
                    msg["triage_reason"] = row.get("reason") or ""
            return {
                "account": provider.account_label(),
                "account_id": account_id,
                "messages": messages,
                "total": len(messages),
                "query": query,
            }
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/send")
    async def send_message(req: InstagramSendRequest, request: Request):
        require_user(request)
        if not (req.text or req.attachments):
            raise HTTPException(400, "Message text or attachments required")
        try:
            provider = _provider(req.account)
            result = await asyncio.to_thread(
                provider.send_message,
                req.text,
                thread_id=req.thread_id,
                username=req.username,
                user_id=req.user_id,
                attachments=req.attachments or [],
            )
            return {"ok": True, "result": result}
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    return router
