import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from backend.models.project import ProjectDetail, ProjectSummary
from backend.services.archive_service import archive_project, restore_project
from backend.services.project_scanner import (
    get_project_by_id,
    invalidate_cache,
    scan_all_projects,
)
from backend.services.thread_service import add_prompt

_SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

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


_REPO_RE = re.compile(r"^PaladinEng/[a-zA-Z0-9][a-zA-Z0-9\-]*$")


class CreateProjectRequest(BaseModel):
    name: str
    repo: str
    description: str


@router.post("/create")
async def create_project(body: CreateProjectRequest):
    """Initiate new project creation. Validates inputs, queues a Claude Code task."""
    if not _REPO_RE.match(body.repo):
        raise HTTPException(
            status_code=400,
            detail="Repo must be PaladinEng/repo-name format",
        )

    project_id = body.repo.split("/")[1].lower()

    existing = get_project_by_id(project_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Project '{project_id}' already exists",
        )

    setup_prompt = f"""Set up a new Paladin Robotics project with these details:

Project name: {body.name}
GitHub repo: {body.repo}
Project ID: {project_id}
Description: {body.description}

Steps:
1. Clone the repo to ~/projects/{project_id}/:
   cd ~/projects && git clone git@github.com:{body.repo}.git

2. Create context/ directory with v1.0 schema files:
   - context/AGENTS.md — session start checklist and rules
   - context/CONTEXT.md — project purpose and architecture
   - context/STATUS.md — current state (initial: "Project created, not yet started")
   - context/DECISIONS.md — empty decisions log with header
   - context/WORKQUEUE.md — empty workqueue with P1/P2/P3 sections
   - context/meta.yaml — name: "{body.name}", slug: {project_id}

3. Create ~/projects/{project_id}/CLAUDE.md with:
   - Project identity and purpose from the description
   - Pointer to read context/ files at session start
   - Standard Paladin architecture invariants
   - Session end requirements (update STATUS.md, commit, print FINISHED WORK)

4. Add to ~/projects/WORKQUEUE-MASTER.md — add a new project section
   with the project name and a note that it is newly created.

5. Create ~/paladin-control/data/projects/{project_id}/ directory
   for thread and prompt queue storage.

6. Commit the initial context files to the repo and push.

When done, write a summary to the paladin-control-plane thread.
"""
    entry = add_prompt("paladin-control-plane", setup_prompt)

    return {
        "status": "queued",
        "project_id": project_id,
        "prompt_id": entry["id"],
        "message": f"Project setup queued. '{project_id}' will appear in dashboard within 2-3 minutes.",
    }


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


_LOG_FILENAME_RE = re.compile(r"^session-[\w\-\.]+\.md$")


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

    log_files = sorted(
        [f.name for f in logs_dir.iterdir()
         if f.name.endswith(".md") and f.name.startswith("session-")],
        reverse=True,
    )
    return [{"filename": f, "size": (logs_dir / f).stat().st_size} for f in log_files]


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

    log_path = Path(project.path) / "logs" / filename
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    content = log_path.read_text(encoding="utf-8")
    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
