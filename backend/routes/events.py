"""
SSE endpoint for real-time push to frontend.
- GET  /api/events  — subscribe to the event stream
- POST /api/events  — push an event (called by Claude Code hooks or other services)
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/events")

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


@router.get("")
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


@router.post("")
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
