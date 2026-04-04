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

from backend.config import DATA_ROOT

_Path = Path


def _atomic_write(path: "_Path", content: str) -> None:
    """Write content to path atomically using temp file + rename."""
    import tempfile
    dir_ = path.parent
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=dir_, delete=False,
            suffix=".tmp", encoding="utf-8"
        ) as tmp:
            tmp.write(content)
            tmp_path = _Path(tmp.name)
        tmp_path.replace(path)
    except Exception:
        if tmp_path:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
        raise


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
    _atomic_write(queue_file, json.dumps(queue, indent=2) + "\n")


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


def add_needs_input_request(project_id: str, question: str, task_id: str) -> dict:
    """
    Add a needs-input entry to the thread.
    Signals the dashboard to show a response input.
    """
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "type": "needs-input",
        "author": "supervisor",
        "project_id": project_id,
        "content": question,
        "task_id": task_id,
        "responded": False,
    }
    thread_file = _project_dir(project_id) / "thread.jsonl"
    with open(thread_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def get_pending_input_request(project_id: str) -> dict | None:
    """Return the most recent unresponded needs-input entry, or None."""
    entries = get_thread(project_id)
    for entry in reversed(entries):
        if entry.get("type") == "needs-input" and not entry.get("responded", False):
            return entry
    return None


def submit_response(
    project_id: str, entry_id: str, response_content: str
) -> dict | None:
    """
    Mark a needs-input entry as responded and write the response file.
    Response written to: ~/paladin-control/data/projects/{project_id}/responses/{entry_id}.json

    Returns None if the entry was already responded (double-tap race guard).
    """
    # Atomically check-and-set: read thread, verify not already responded,
    # then mark responded — all in one file read/write cycle.
    thread_file = _project_dir(project_id) / "thread.jsonl"
    already_responded = False
    if thread_file.exists():
        lines = thread_file.read_text(encoding="utf-8").splitlines()
        updated_lines = []
        for line in lines:
            try:
                entry = json.loads(line)
                if entry.get("id") == entry_id:
                    if entry.get("responded", False):
                        already_responded = True
                    entry["responded"] = True
                updated_lines.append(json.dumps(entry))
            except json.JSONDecodeError:
                updated_lines.append(line)
        _atomic_write(thread_file, "\n".join(updated_lines) + "\n")

    if already_responded:
        return None

    # Write response file for the waiting task to read
    responses_dir = _project_dir(project_id) / "responses"
    responses_dir.mkdir(exist_ok=True)
    response_data = {
        "entry_id": entry_id,
        "response": response_content,
        "timestamp": _now_iso(),
    }
    (responses_dir / f"{entry_id}.json").write_text(
        json.dumps(response_data, indent=2), encoding="utf-8"
    )

    # Add user response entry to thread
    response_entry = add_thread_entry(
        project_id, "response", "user", response_content
    )
    return response_entry


def get_response_file(project_id: str, entry_id: str) -> dict | None:
    """Read a response file. Returns None if not yet written."""
    response_file = _project_dir(project_id) / "responses" / f"{entry_id}.json"
    if not response_file.exists():
        return None
    try:
        return json.loads(response_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
