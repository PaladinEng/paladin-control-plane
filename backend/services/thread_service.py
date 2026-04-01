"""
Thread service — manages per-project chat threads and prompt queues.

Thread entries are stored as append-only JSONL at:
  ~/paladin-control/data/projects/{project_id}/thread.jsonl

Prompt queues are stored as JSON arrays at:
  ~/paladin-control/data/projects/{project_id}/prompt-queue.json
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA_ROOT = Path.home() / "paladin-control" / "data" / "projects"


def _project_dir(project_id: str) -> Path:
    d = DATA_ROOT / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_entry(
    project_id: str,
    entry_type: str,
    author: str,
    content: str,
    handled: Optional[bool] = None,
) -> dict:
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "type": entry_type,
        "author": author,
        "project_id": project_id,
        "content": content,
    }
    if entry_type == "prompt":
        entry["handled"] = handled if handled is not None else False
    return entry


def get_thread(project_id: str) -> list[dict]:
    """Return thread entries for a project, newest last, max 100."""
    thread_file = _project_dir(project_id) / "thread.jsonl"
    if not thread_file.exists():
        return []
    entries = []
    for line in thread_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries[-100:]


def add_thread_entry(
    project_id: str, entry_type: str, author: str, content: str
) -> dict:
    """Append a new entry to the thread JSONL file."""
    entry = _make_entry(project_id, entry_type, author, content)
    thread_file = _project_dir(project_id) / "thread.jsonl"
    with open(thread_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def get_prompt_queue(project_id: str) -> list[dict]:
    """Return unhandled prompt entries from the queue."""
    queue_file = _project_dir(project_id) / "prompt-queue.json"
    if not queue_file.exists():
        return []
    try:
        data = json.loads(queue_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [e for e in data if not e.get("handled", False)]


def _read_full_queue(project_id: str) -> list[dict]:
    """Read the entire prompt queue (handled + unhandled)."""
    queue_file = _project_dir(project_id) / "prompt-queue.json"
    if not queue_file.exists():
        return []
    try:
        return json.loads(queue_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _write_queue(project_id: str, queue: list[dict]) -> None:
    """Write the full prompt queue to disk."""
    queue_file = _project_dir(project_id) / "prompt-queue.json"
    queue_file.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")


def add_prompt(project_id: str, content: str) -> dict:
    """Add a user prompt to both the thread and the prompt queue."""
    entry = _make_entry(project_id, "prompt", "user", content, handled=False)

    # Append to thread
    thread_file = _project_dir(project_id) / "thread.jsonl"
    with open(thread_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    # Append to prompt queue
    queue = _read_full_queue(project_id)
    queue.append(entry)
    _write_queue(project_id, queue)

    return entry


def mark_prompt_handled(project_id: str, prompt_id: str) -> bool:
    """Set handled=true for a prompt in the queue. Returns True if found."""
    queue = _read_full_queue(project_id)
    found = False
    for entry in queue:
        if entry.get("id") == prompt_id:
            entry["handled"] = True
            found = True
            break
    if found:
        _write_queue(project_id, queue)
    return found
