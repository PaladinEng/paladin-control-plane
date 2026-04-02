"""
Scans ~/projects/*/context/ directories to build project state.
Results are cached for 30 seconds.
"""

import os
import re
import time
from pathlib import Path
from typing import Optional

import yaml

from backend.models.project import ProjectDetail, ProjectSummary
from backend.services.archive_service import is_archived

PROJECTS_ROOT = Path.home() / "projects"
CACHE_TTL = 30  # seconds

_cache: dict = {"ts": 0.0, "data": None}


def _read_file(path: Path) -> Optional[str]:
    """Read a file, returning None if it doesn't exist or can't be read."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _extract_current_state(status_md: str) -> str:
    """Extract first paragraph from ## Current State section."""
    match = re.search(r"##\s+Current State\s*\n(.*?)(?=\n##|\Z)", status_md, re.DOTALL)
    if not match:
        # Fall back to the first non-empty paragraph in the file
        for line in status_md.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
        return ""
    section = match.group(1).strip()
    # Return just the first paragraph (up to first blank line)
    first_para = section.split("\n\n")[0].strip()
    return first_para


def _extract_active_tasks(workqueue_md: str) -> list[str]:
    """Extract unchecked items from ## Active Sprint section."""
    match = re.search(r"##\s+Active Sprint\s*\n(.*?)(?=\n##|\Z)", workqueue_md, re.DOTALL)
    if not match:
        return []
    section = match.group(1)
    tasks = []
    for line in section.splitlines():
        # Match "- [ ] ..." lines (unchecked tasks)
        m = re.match(r"\s*-\s+\[\s*\]\s+(.*)", line)
        if m:
            tasks.append(m.group(1).strip())
    return tasks


def _determine_status(
    status_md: str, workqueue_md: Optional[str], project_id: str = ""
) -> str:
    """
    Determine project status in priority order:
    - 'needs-input' if unresponded needs-input entry in thread
    - 'running'     if CPO active/ has a task for this project
    - 'queued'      if prompt-queue.json has unhandled prompts
    - 'active'      if WORKQUEUE.md has unchecked Active Sprint items
    - 'idle'        otherwise
    """
    # 1. Check needs-input (existing logic)
    if project_id:
        try:
            from backend.services.thread_service import get_pending_input_request

            if get_pending_input_request(project_id) is not None:
                return "needs-input"
        except Exception:
            pass

    # 2. Check CPO active queue for this project
    if project_id:
        try:
            cpo_active = Path.home() / "dev" / "queue" / "active"
            if cpo_active.exists():
                for task_dir in cpo_active.iterdir():
                    if task_dir.is_dir() and task_dir.name.startswith(project_id):
                        return "running"
        except Exception:
            pass

    # 3. Check prompt queue for unhandled prompts
    if project_id:
        try:
            from backend.services.thread_service import get_prompt_queue

            if get_prompt_queue(project_id):
                return "queued"
        except Exception:
            pass

    # 4. Check WORKQUEUE.md Active Sprint
    if workqueue_md:
        active_tasks = _extract_active_tasks(workqueue_md)
        if active_tasks:
            return "active"

    return "idle"


def _scan_project(project_dir: Path) -> Optional[ProjectDetail]:
    """Scan a single project directory and return a ProjectDetail, or None if not a valid project."""
    context_dir = project_dir / "context"
    status_path = context_dir / "STATUS.md"

    if not status_path.exists():
        return None

    status_raw = _read_file(status_path) or ""
    workqueue_raw = _read_file(context_dir / "WORKQUEUE.md") or ""
    decisions_raw = _read_file(context_dir / "DECISIONS.md")

    # Read meta.yaml for optional metadata
    meta: dict = {}
    meta_text = _read_file(context_dir / "meta.yaml")
    if meta_text:
        try:
            meta = yaml.safe_load(meta_text) or {}
        except Exception:
            meta = {}

    project_id = project_dir.name
    project_name = meta.get("name", project_id.replace("-", " ").title())

    # Collect recent session logs
    logs_dir = project_dir / "logs"
    recent_sessions: list[str] = []
    if logs_dir.exists():
        try:
            session_files = sorted(
                [f.name for f in logs_dir.iterdir() if f.name.startswith("session-")],
                reverse=True,
            )
            recent_sessions = session_files[:10]
        except Exception:
            pass

    # Last-updated: prefer meta.yaml, then STATUS.md first-line date, then file mtime
    last_updated: Optional[str] = meta.get("last_updated")
    if not last_updated:
        for line in status_raw.splitlines():
            m = re.search(r"\d{4}-\d{2}-\d{2}", line)
            if m:
                last_updated = m.group(0)
                break
    if not last_updated:
        try:
            last_updated = time.strftime(
                "%Y-%m-%d", time.localtime(status_path.stat().st_mtime)
            )
        except Exception:
            pass

    return ProjectDetail(
        id=project_id,
        name=project_name,
        path=str(project_dir),
        status=_determine_status(status_raw, workqueue_raw, project_id),
        current_state=_extract_current_state(status_raw) if status_raw else "",
        active_tasks=_extract_active_tasks(workqueue_raw) if workqueue_raw else [],
        last_updated=last_updated,
        archived=is_archived(project_id),
        workqueue_raw=workqueue_raw,
        status_raw=status_raw,
        decisions_raw=decisions_raw,
        recent_sessions=recent_sessions,
    )


def scan_all_projects() -> list[ProjectDetail]:
    """Return all projects, using cache if fresh."""
    now = time.monotonic()
    # Use shorter TTL if any project is in an active state
    ttl = CACHE_TTL
    if _cache["data"]:
        active_states = {"running", "queued", "needs-input"}
        if any(p.status in active_states for p in _cache["data"]):
            ttl = 10  # refresh faster when work is happening
    if _cache["data"] is not None and (now - _cache["ts"]) < ttl:
        return _cache["data"]

    projects: list[ProjectDetail] = []
    try:
        for entry in sorted(PROJECTS_ROOT.iterdir()):
            if not entry.is_dir():
                continue
            # Skip hidden dirs and the .venv, __pycache__, etc.
            if entry.name.startswith(".") or entry.name.startswith("_"):
                continue
            project = _scan_project(entry)
            if project is not None:
                projects.append(project)
    except Exception:
        pass

    _cache["ts"] = now
    _cache["data"] = projects
    return projects


def get_project_by_id(project_id: str) -> Optional[ProjectDetail]:
    """Return a single project by ID, or None if not found."""
    for project in scan_all_projects():
        if project.id == project_id:
            return project
    return None


def invalidate_cache() -> None:
    """Force the next call to rescan."""
    _cache["ts"] = 0.0
    _cache["data"] = None
