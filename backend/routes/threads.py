"""
Thread and prompt endpoints for per-project chat.

GET  /api/projects/{id}/thread  — list thread entries
POST /api/projects/{id}/prompt  — submit a user prompt
POST /api/projects/{id}/prompts/batch  — submit multiple prompts
POST /api/projects/{id}/prompts/upload — upload .md/.txt file of prompts
"""

import re

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel

from backend.routes.events import broadcast_project_update
from backend.utils.prompt_parser import parse_prompts

_SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

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


def _validate_project_id(project_id: str) -> None:
    if not _SLUG_RE.match(project_id):
        raise HTTPException(status_code=400, detail="Invalid project_id")


@router.get("/{project_id}/thread")
async def list_thread(project_id: str):
    """Return thread entries for a project (newest last, max 100)."""
    _validate_project_id(project_id)
    return get_thread(project_id)


@router.post("/{project_id}/prompt")
async def submit_prompt(project_id: str, body: PromptRequest, request: Request):
    """Submit a user prompt — adds to thread and prompt queue."""
    _validate_project_id(project_id)
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Content must not be empty")

    entry = add_prompt(project_id, body.content.strip())
    broadcast_project_update(project_id, "thread_update")
    return entry


@router.post("/{project_id}/respond")
async def submit_response_endpoint(
    project_id: str, body: RespondRequest, request: Request
):
    """Submit a response to a paused needs-input request."""
    _validate_project_id(project_id)
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Response must not be empty")

    pending = get_pending_input_request(project_id)
    if pending is None:
        raise HTTPException(
            status_code=409,
            detail="No pending needs-input request — already responded?",
        )

    response_entry = submit_response(project_id, pending["id"], body.content.strip())

    # Double-tap race: submit_response returns None if already responded
    if response_entry is None:
        raise HTTPException(
            status_code=409,
            detail="Already responded to this needs-input request",
        )

    # Invalidate project scanner cache so status updates
    from backend.services.project_scanner import invalidate_cache
    invalidate_cache()

    broadcast_project_update(project_id, "thread_update", "status_update")

    return response_entry


class BatchPromptRequest(BaseModel):
    prompts: list[str]


@router.post("/{project_id}/prompts/batch")
async def submit_batch_prompts(
    project_id: str, body: BatchPromptRequest, request: Request
):
    """Submit multiple prompts at once — queued and executed in order."""
    _validate_project_id(project_id)

    if not body.prompts:
        raise HTTPException(status_code=400, detail="No prompts provided")

    if len(body.prompts) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximum 50 prompts per batch",
        )

    entries = []
    for content in body.prompts:
        content = content.strip()
        if not content:
            continue
        entry = add_prompt(project_id, content)
        entries.append(entry)

    broadcast_project_update(project_id, "thread_update")

    return {
        "queued": len(entries),
        "prompt_ids": [e["id"] for e in entries],
    }


@router.post("/{project_id}/prompts/upload")
async def upload_prompt_file(
    project_id: str,
    file: UploadFile = File(...),
    request: Request = None,
):
    """Upload a .md or .txt file and queue each section as a prompt."""
    _validate_project_id(project_id)

    if file.content_type not in (
        "text/plain",
        "text/markdown",
        "application/octet-stream",
    ) and not (file.filename or "").endswith((".md", ".txt")):
        raise HTTPException(
            status_code=400,
            detail="Only .md and .txt files accepted",
        )

    content = (await file.read()).decode("utf-8", errors="replace")
    prompts = parse_prompts(content)

    if not prompts:
        raise HTTPException(status_code=400, detail="No prompts found in file")

    if len(prompts) > 50:
        raise HTTPException(
            status_code=400,
            detail=f"File contains {len(prompts)} prompts — maximum is 50",
        )

    entries = []
    for p in prompts:
        entry = add_prompt(project_id, p)
        entries.append(entry)

    broadcast_project_update(project_id, "thread_update")

    return {
        "queued": len(entries),
        "filename": file.filename,
        "prompt_ids": [e["id"] for e in entries],
        "preview": [p[:80] + "..." if len(p) > 80 else p for p in prompts],
    }
