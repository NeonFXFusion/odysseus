"""Small owner-scoped cache for Instagram DM triage tags."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from routes.email_helpers import SCHEDULED_DB


def init_instagram_tags_db() -> None:
    conn = sqlite3.connect(SCHEDULED_DB)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS instagram_tags (
                account_id TEXT NOT NULL,
                owner TEXT DEFAULT '',
                thread_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                thread_title TEXT,
                username TEXT,
                text_preview TEXT,
                tags TEXT,
                score INTEGER DEFAULT 0,
                reason TEXT,
                model_used TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (account_id, owner, thread_id, message_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_instagram_tags_owner_account "
            "ON instagram_tags(owner, account_id, thread_id)"
        )
        conn.commit()
    finally:
        conn.close()


def _loads_tags(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    out = []
    for tag in parsed:
        tag = str(tag or "").strip().lower().replace("_", "-")
        if tag and tag not in out:
            out.append(tag)
    return out


def _row_to_tag(row) -> dict[str, Any]:
    return {
        "account_id": row[0],
        "owner": row[1] or "",
        "thread_id": row[2],
        "message_id": row[3],
        "thread_title": row[4] or "",
        "username": row[5] or "",
        "text_preview": row[6] or "",
        "tags": _loads_tags(row[7]),
        "score": int(row[8] or 0),
        "reason": row[9] or "",
        "model_used": row[10] or "",
        "created_at": row[11] or "",
    }


def get_instagram_tag_rows(
    *,
    owner: str = "",
    account_id: str | None = None,
    thread_id: str | None = None,
) -> list[dict[str, Any]]:
    init_instagram_tags_db()
    where = ["owner = ?"]
    params: list[Any] = [owner or ""]
    if account_id:
        where.append("account_id = ?")
        params.append(account_id)
    if thread_id:
        where.append("thread_id = ?")
        params.append(thread_id)
    conn = sqlite3.connect(SCHEDULED_DB)
    try:
        rows = conn.execute(
            "SELECT account_id, owner, thread_id, message_id, thread_title, username, "
            "text_preview, tags, score, reason, model_used, created_at "
            f"FROM instagram_tags WHERE {' AND '.join(where)} "
            "ORDER BY score DESC, created_at DESC",
            params,
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_tag(row) for row in rows]


def upsert_instagram_tag(row: dict[str, Any]) -> None:
    init_instagram_tags_db()
    tags = []
    for tag in row.get("tags") or []:
        tag = str(tag or "").strip().lower().replace("_", "-")
        if tag and tag not in tags:
            tags.append(tag)
    conn = sqlite3.connect(SCHEDULED_DB)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO instagram_tags
            (account_id, owner, thread_id, message_id, thread_title, username,
             text_preview, tags, score, reason, model_used, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(row.get("account_id") or ""),
                str(row.get("owner") or ""),
                str(row.get("thread_id") or ""),
                str(row.get("message_id") or ""),
                str(row.get("thread_title") or "")[:240],
                str(row.get("username") or "")[:120],
                str(row.get("text_preview") or "")[:500],
                json.dumps(tags),
                int(row.get("score") or 0),
                str(row.get("reason") or "")[:300],
                str(row.get("model_used") or "")[:160],
                row.get("created_at") or datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def attach_instagram_tags(thread: dict[str, Any], *, owner: str = "", account_id: str = "") -> dict[str, Any]:
    rows = get_instagram_tag_rows(owner=owner or "", account_id=account_id or None, thread_id=thread.get("thread_id") or None)
    by_message = {str(row.get("message_id") or ""): row for row in rows}
    aggregate_tags: list[str] = []
    max_score = 0
    for msg in thread.get("messages") or []:
        row = by_message.get(str(msg.get("message_id") or ""))
        if not row:
            continue
        msg["tags"] = row.get("tags") or []
        msg["triage_score"] = row.get("score", 0)
        msg["triage_reason"] = row.get("reason") or ""
        max_score = max(max_score, int(row.get("score") or 0))
        for tag in row.get("tags") or []:
            if tag not in aggregate_tags:
                aggregate_tags.append(tag)
    thread["tags"] = aggregate_tags
    thread["triage_score"] = max_score
    return thread


def clear_instagram_tags(*, owner: str = "") -> int:
    init_instagram_tags_db()
    conn = sqlite3.connect(SCHEDULED_DB)
    try:
        if owner:
            before = conn.execute("SELECT COUNT(*) FROM instagram_tags WHERE owner = ?", (owner,)).fetchone()[0]
            conn.execute("DELETE FROM instagram_tags WHERE owner = ?", (owner,))
        else:
            before = conn.execute("SELECT COUNT(*) FROM instagram_tags").fetchone()[0]
            conn.execute("DELETE FROM instagram_tags")
        conn.commit()
        return int(before or 0)
    finally:
        conn.close()
