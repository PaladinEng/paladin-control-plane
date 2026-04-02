"""
Archive/restore service for projects.

State is persisted in ~/paladin-control/data/projects/{id}/state.json.
"""

import json
import re
from pathlib import Path

from backend.config import DATA_ROOT

_SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _state_path(project_id: str) -> Path:
    return DATA_ROOT / project_id / "state.json"


def _read_state(project_id: str) -> dict:
    path = _state_path(project_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_state(project_id: str, state: dict) -> None:
    path = _state_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(path)


def is_archived(project_id: str) -> bool:
    state = _read_state(project_id)
    return state.get("archived", False)


def archive_project(project_id: str) -> dict:
    if not _SLUG_RE.match(project_id):
        raise ValueError("Invalid project_id")
    state = _read_state(project_id)
    state["archived"] = True
    _write_state(project_id, state)
    return {"status": "archived", "project_id": project_id}


def restore_project(project_id: str) -> dict:
    if not _SLUG_RE.match(project_id):
        raise ValueError("Invalid project_id")
    state = _read_state(project_id)
    state["archived"] = False
    _write_state(project_id, state)
    return {"status": "active", "project_id": project_id}
