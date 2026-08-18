"""Opaque, chronological cursor pagination helpers for API list endpoints."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, or_


DEFAULT_PAGE_SIZE = 8
MAX_PAGE_SIZE = 50


def _encode(timestamp: datetime, identifier: Any) -> str:
    payload = json.dumps({"at": timestamp.isoformat(), "id": str(identifier)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode(cursor: str, identifier_type: type) -> tuple[datetime, Any]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        return datetime.fromisoformat(payload["at"]), identifier_type(payload["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid cursor") from exc


def chronological_page(query, model, timestamp_column, cursor: str | None, limit: int):
    """Return newest-first rows plus an opaque seek cursor for the next page."""
    page_size = min(max(limit, 1), MAX_PAGE_SIZE)
    if cursor:
        cursor_at, cursor_id = _decode(cursor, model.id.type.python_type)
        query = query.filter(or_(timestamp_column < cursor_at, and_(timestamp_column == cursor_at, model.id < cursor_id)))
    rows = query.order_by(timestamp_column.desc(), model.id.desc()).limit(page_size + 1).all()
    items = rows[:page_size]
    next_cursor = _encode(getattr(items[-1], timestamp_column.key), items[-1].id) if len(rows) > page_size else None
    return items, next_cursor
