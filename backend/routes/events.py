"""
SSE endpoint for real-time push to frontend.
- GET  /api/events  — subscribe to the event stream
- POST /api/events  — push an event (called by Claude Code hooks or other services)
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator

import re
import subprocess

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

router = APIRouter()


class NeedsInputRequest(BaseModel):
    question: str
    task_id: str

# In-memory event queue shared across all SSE subscribers
_subscribers: list[asyncio.Queue] = []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _event_generator(request: Request) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.append(queue)
    try:
        # Send an initial connection acknowledgement
        yield f"event: connected\ndata: {json.dumps({'timestamp': _now_iso()})}\n\n"

        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                # Wait for a new event or send heartbeat after 15s
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield event
            except asyncio.TimeoutError:
                # Heartbeat to keep the connection alive
                yield f"event: heartbeat\ndata: {json.dumps({'timestamp': _now_iso()})}\n\n"
    finally:
        _subscribers.remove(queue)


@router.get("/api/events")
async def subscribe_events(request: Request):
    """SSE endpoint — clients connect here for real-time updates."""
    return StreamingResponse(
        _event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/events")
async def publish_event(request: Request):
    """
    Receive an event payload and broadcast it to all SSE subscribers.
    Expected JSON body: {"type": "...", "project_id": "...", "data": {...}}
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    event_type = body.get("type", "update")
    payload = json.dumps({"timestamp": _now_iso(), **body})
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

    return {"status": "ok", "delivered_to": len(_subscribers) - len(dead)}


@router.post("/api/projects/{project_id}/needs-input")
async def request_input(project_id: str, body: NeedsInputRequest):
    """Signal that a task needs user input before continuing."""
    if not _SLUG_RE.match(project_id):
        raise HTTPException(status_code=400, detail="Invalid project_id")

    from backend.services.thread_service import add_needs_input_request
    from backend.services.project_scanner import invalidate_cache

    entry = add_needs_input_request(project_id, body.question, body.task_id)

    # Invalidate scanner cache so status reflects needs-input
    invalidate_cache()

    # Send ntfy notification
    try:
        subprocess.run(
            [
                "curl", "-s", "-X", "POST", "http://localhost:8090/paladin-alerts",
                "-H", f"Title: Input needed — {project_id}",
                "-H", "Priority: high",
                "-H", "Tags: pause_button",
                "-H", f"Click: https://dashboard.paladinrobotics.com/#/project/{project_id}",
                "-d", body.question,
            ],
            timeout=5,
            capture_output=True,
        )
    except Exception:
        pass  # ntfy failure is non-fatal

    # Broadcast SSE events
    for event_type in ("thread_update", "status_update"):
        payload = json.dumps({
            "type": event_type,
            "project_id": project_id,
            "timestamp": _now_iso(),
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

    return entry
