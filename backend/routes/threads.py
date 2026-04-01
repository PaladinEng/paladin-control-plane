"""
Thread and prompt endpoints for per-project chat.

GET  /api/projects/{id}/thread  — list thread entries
POST /api/projects/{id}/prompt  — submit a user prompt
"""

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.services.thread_service import add_prompt, get_thread

router = APIRouter(prefix="/api/projects")


class PromptRequest(BaseModel):
    content: str


@router.get("/{project_id}/thread")
async def list_thread(project_id: str):
    """Return thread entries for a project (newest last, max 100)."""
    return get_thread(project_id)


@router.post("/{project_id}/prompt")
async def submit_prompt(project_id: str, body: PromptRequest, request: Request):
    """Submit a user prompt — adds to thread and prompt queue."""
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Content must not be empty")

    entry = add_prompt(project_id, body.content.strip())

    # Broadcast SSE event for thread update
    # Import here to avoid circular imports
    from backend.routes.events import _subscribers

    payload = json.dumps({
        "type": "thread_update",
        "project_id": project_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    sse_message = f"event: thread_update\ndata: {payload}\n\n"

    dead: list[asyncio.Queue] = []
    for q in _subscribers:
        try:
            q.put_nowait(sse_message)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass

    return entry
