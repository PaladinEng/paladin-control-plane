import json
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path as _Path
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from backend.models.project import ProjectDetail, ProjectSummary
from backend.routes.events import broadcast_project_update
from backend.config import DATA_ROOT
from backend.services.archive_service import archive_project, restore_project
from backend.services.project_scanner import (
    get_project_by_id,
    invalidate_cache,
    scan_all_projects,
)
from backend.services.thread_service import add_prompt

Path = _Path

PALADIN_CONFIG_PATH = Path.home() / "projects" / ".paladin-config.yaml"
UPLOADS_DIR = Path.home() / "paladin-control" / "data" / "uploads"
CPO_PENDING = Path.home() / "dev" / "queue" / "pending"

_SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _safe_log_path(logs_dir: "_Path", filename: str) -> "_Path | None":
    """Return resolved path only if it stays within logs_dir."""
    if "/" in filename or "\\" in filename or "\x00" in filename:
        return None
    try:
        resolved = (logs_dir / filename).resolve()
        resolved.relative_to(logs_dir.resolve())
        return resolved
    except ValueError:
        return None

router = APIRouter(prefix="/api/projects")


def _validate_project_id(project_id: str) -> None:
    if not _SLUG_RE.match(project_id):
        raise HTTPException(status_code=400, detail="Invalid project_id")


@router.get("", response_model=list[ProjectSummary])
async def list_projects():
    """Return all projects with summary status."""
    projects = scan_all_projects()
    return [ProjectSummary(**p.model_dump()) for p in projects]


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: str):
    """Return full detail for a single project."""
    project = get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return project


@router.post("/{project_id}/archive")
async def archive(project_id: str):
    """Archive a project — moves it to the collapsed archived section."""
    _validate_project_id(project_id)
    project = get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    result = archive_project(project_id)
    invalidate_cache()
    return result


@router.post("/{project_id}/restore")
async def restore(project_id: str):
    """Restore an archived project back to active."""
    _validate_project_id(project_id)
    project = get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    result = restore_project(project_id)
    invalidate_cache()
    return result


def _load_paladin_config() -> dict:
    """Read .paladin-config.yaml. Returns empty defaults if missing."""
    if not PALADIN_CONFIG_PATH.exists():
        return {"ignore_directories": [], "compliance": {}}
    try:
        return yaml.safe_load(PALADIN_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"ignore_directories": [], "compliance": {}}


_VALID_MODES = {"existing-repo", "new-repo", "imported-repo", "prompted-start"}


class CreateProjectRequest(BaseModel):
    mode: str
    name: str
    owner: str = "PaladinEng"
    private: bool = True
    brief: Optional[str] = None
    brief_file_path: Optional[str] = None
    github_url: Optional[str] = None
    description: Optional[str] = None
    tech_preferences: Optional[str] = None


@router.post("/create")
async def create_project(body: CreateProjectRequest):
    """Initiate new project creation per spec v1.1 — validates, writes CPO task."""
    if body.mode not in _VALID_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {body.mode}")

    # Derive slug from name or github_url
    if body.mode in ("existing-repo", "imported-repo"):
        if not body.github_url:
            raise HTTPException(status_code=400, detail="github_url required for this mode")
        slug = body.github_url.rstrip("/").split("/")[-1].lower()
        if slug.endswith(".git"):
            slug = slug[:-4]
    else:
        slug = re.sub(r"[^a-z0-9-]", "-", body.name.lower().strip()).strip("-")
        if not slug:
            raise HTTPException(status_code=400, detail="Invalid project name")

    if not _SLUG_RE.match(slug):
        raise HTTPException(status_code=400, detail=f"Invalid slug: {slug}")

    # Check ignore list
    config = _load_paladin_config()
    ignore_dirs = config.get("ignore_directories", [])
    if slug in ignore_dirs:
        raise HTTPException(
            status_code=409,
            detail=f"'{slug}' is in the ignore list and cannot be used as a project name",
        )

    # Check if project already exists in scanner
    existing = get_project_by_id(slug)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Project '{slug}' already exists")

    # Check local directory — only for modes that create a new directory.
    # existing-repo and imported-repo expect the local directory to already exist.
    projects_root = Path.home() / "projects"
    if body.mode in ("new-repo", "prompted-start") and (projects_root / slug).exists():
        raise HTTPException(
            status_code=409,
            detail=f"Directory ~/projects/{slug} already exists",
        )

    # Check runtime data
    runtime_dir = DATA_ROOT / slug
    meta_json = runtime_dir / "meta.json"
    if meta_json.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Runtime data for '{slug}' already exists",
        )

    # Build task payload
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    task_id = f"create-{slug}-{timestamp}"
    payload = {
        "mode": body.mode,
        "slug": slug,
        "name": body.name,
        "owner": body.owner,
        "private": body.private,
        "brief": body.brief,
        "brief_file_path": body.brief_file_path,
        "github_url": body.github_url,
        "description": body.description,
        "tech_preferences": body.tech_preferences,
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Write CPO task to pending queue
    task_dir = CPO_PENDING / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    # Generate the task prompt via create_project.py
    from supervisor.create_project import generate_creation_prompt

    task_prompt = generate_creation_prompt(payload)
    (task_dir / "task.md").write_text(task_prompt, encoding="utf-8")
    (task_dir / "payload.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    # Status file for queue runner
    (task_dir / "status.json").write_text(
        json.dumps({"status": "pending", "project_id": slug, "task_id": task_id}),
        encoding="utf-8",
    )

    # Create minimal runtime data so project appears immediately as provisioning
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "meta.json").write_text(
        json.dumps({
            "id": slug,
            "name": body.name,
            "mode": body.mode,
            "github_url": body.github_url or f"https://github.com/{body.owner}/{slug}",
            "local_path": str(projects_root / slug),
            "status": "provisioning",
            "created_at": payload["created_at"],
        }, indent=2),
        encoding="utf-8",
    )
    (runtime_dir / "thread.jsonl").write_text("", encoding="utf-8")
    (runtime_dir / "prompt-queue.json").write_text("[]", encoding="utf-8")

    invalidate_cache()
    broadcast_project_update(slug, "status_update", status="provisioning")

    return {
        "project_id": slug,
        "task_id": task_id,
        "status": "provisioning",
    }


@router.post("/{project_id}/provisioning-complete")
async def provisioning_complete(project_id: str):
    """Called by Claude Code after successful project creation and self-validation."""
    _validate_project_id(project_id)

    # Update meta.json status to idle
    runtime_dir = DATA_ROOT / project_id
    meta_json = runtime_dir / "meta.json"
    if meta_json.exists():
        try:
            meta = json.loads(meta_json.read_text(encoding="utf-8"))
            meta["status"] = "idle"
            meta_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except Exception:
            pass

    invalidate_cache()
    broadcast_project_update(project_id, "status_update", status="idle")

    # Send ntfy notification
    try:
        subprocess.run(
            [
                "curl", "-s", "-X", "POST", "http://localhost:8090/paladin-alerts",
                "-H", f"Title: Project created — {project_id}",
                "-H", "Priority: default",
                "-H", "Tags: white_check_mark",
                "-H", f"Click: https://dashboard.paladinrobotics.com/#/project/{project_id}",
                "-d", f"Project {project_id} has been provisioned and is ready.",
            ],
            timeout=5,
            capture_output=True,
        )
    except Exception:
        pass

    return {"status": "idle", "project_id": project_id}


@router.post("/uploads")
async def upload_brief(file: UploadFile = File(...)):
    """Upload a brief file (.md, .txt, .pdf) for prompted-start mode."""
    filename = file.filename or "brief.txt"
    allowed_ext = (".md", ".txt", ".pdf")
    if not any(filename.lower().endswith(ext) for ext in allowed_ext):
        raise HTTPException(status_code=400, detail="Only .md, .txt, .pdf files accepted")

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    dest = UPLOADS_DIR / f"{timestamp}-{safe_name}"

    content = await file.read()
    dest.write_bytes(content)

    return {"path": str(dest), "filename": safe_name}


class AddTaskRequest(BaseModel):
    title: str
    priority: str  # P1, P2, P3
    description: str = ""
    overnight_ready: bool = False
    blast_radius: str = "LOW"


@router.post("/{project_id}/workqueue/add")
async def add_workqueue_task(project_id: str, body: AddTaskRequest):
    """Add a new task to the project WORKQUEUE.md."""
    _validate_project_id(project_id)
    project = get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.priority not in ("P1", "P2", "P3"):
        raise HTTPException(status_code=400, detail="Priority must be P1, P2, or P3")

    workqueue_path = Path(project.path) / "context" / "WORKQUEUE.md"
    if not workqueue_path.exists():
        raise HTTPException(status_code=404, detail="WORKQUEUE.md not found")

    notes_line = f"\nnotes: {body.description}" if body.description else ""
    task_block = (
        f"\n### [{body.priority}-NEW] {body.title}\n"
        f"project: {project_id}\n"
        f"parallel: YES\n"
        f"blast-radius: {body.blast_radius}\n"
        f"overnight-ready: {'YES' if body.overnight_ready else 'NO'}\n"
        f"added: {date.today().isoformat()}{notes_line}\n"
        f"done-when:\n"
        f"  - (fill in acceptance criteria)\n"
    )

    content = workqueue_path.read_text(encoding="utf-8")

    # Map priority to the section header it belongs under
    section_map = {"P1": "## Active Sprint", "P2": "## P3 Backlog", "P3": "## P3 Backlog"}
    section_marker = section_map[body.priority]

    if section_marker in content:
        idx = content.index(section_marker)
        line_end = content.index("\n", idx) + 1
        content = content[:line_end] + task_block + content[line_end:]
    else:
        content += f"\n{task_block}"

    workqueue_path.write_text(content, encoding="utf-8")
    invalidate_cache()

    return {
        "status": "added",
        "title": body.title,
        "priority": body.priority,
    }


_LOG_FILENAME_RE = re.compile(r"^(session|prompt)-[\w\-\.]+\.md$")


@router.get("/{project_id}/logs")
async def list_logs(project_id: str):
    """Return list of session log filenames for a project."""
    _validate_project_id(project_id)
    project = get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    logs_dir = Path(project.path) / "logs"
    if not logs_dir.exists():
        return []

    logs = []

    # Session logs
    for f in sorted(logs_dir.glob("session-*.md"), reverse=True):
        logs.append({
            "filename": f.name,
            "type": "session",
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
        })

    # Prompt execution logs
    for f in sorted(logs_dir.glob("prompt-*.md"), reverse=True)[:50]:
        logs.append({
            "filename": f.name,
            "type": "prompt",
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
        })

    # Sort all logs by modified time, newest first
    logs.sort(key=lambda x: x["modified"], reverse=True)
    return logs


@router.get("/{project_id}/logs/{filename}")
async def download_log(project_id: str, filename: str):
    """Serve a session log file for download."""
    _validate_project_id(project_id)
    project = get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    # Validate filename — prevent path traversal
    if not _LOG_FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    logs_dir = Path(project.path) / "logs"
    log_path = _safe_log_path(logs_dir, filename)
    if log_path is None:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    content = log_path.read_text(encoding="utf-8")
    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
