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

from backend.services.thread_service import (
    add_prompt,
    get_pending_input_request,
    get_thread,
    submit_response,
)

router = APIRouter(prefix="/api/projects")


class PromptRequest(BaseModel):
    content: str


class RespondRequest(BaseModel):
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
    _broadcast_sse("thread_update", project_id)
    return entry


def _broadcast_sse(event_type: str, project_id: str) -> None:
    """Broadcast an SSE event to all subscribers."""
    from backend.routes.events import _subscribers

    payload = json.dumps({
        "type": event_type,
        "project_id": project_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    sse_message = f"event: {event_type}\ndata: {payload}\n\n"

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


@router.post("/{project_id}/respond")
async def submit_response_endpoint(
    project_id: str, body: RespondRequest, request: Request
):
    """Submit a response to a paused needs-input request."""
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Response must not be empty")

    pending = get_pending_input_request(project_id)
    if pending is None:
        raise HTTPException(
            status_code=404,
            detail="No pending needs-input request for this project",
        )

    response_entry = submit_response(project_id, pending["id"], body.content.strip())

    # Invalidate project scanner cache so status updates
    from backend.services.project_scanner import invalidate_cache
    invalidate_cache()

    _broadcast_sse("thread_update", project_id)
    _broadcast_sse("status_update", project_id)

    return response_entry
