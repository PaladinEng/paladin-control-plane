"""
Meta-supervisor prompt handler.

Polls all project prompt queues for unhandled prompts and routes each one
to a CPO task directory for execution by queue-worker-full-pass.sh.

Runs as a systemd user service (paladin-supervisor.service).
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path so we can import backend modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.thread_service import (
    add_thread_entry,
    get_prompt_queue,
    mark_prompt_handled,
)

# Configuration
DATA_ROOT = Path.home() / "paladin-control" / "data" / "projects"
QUEUE_ROOT = Path.home() / "dev" / "queue" / "pending"
POLL_INTERVAL = 60  # seconds
PID_FILE = Path.home() / "paladin-control" / "supervisor.pid"
LOG_FILE = PROJECT_ROOT / "logs" / "supervisor.log"
API_BASE = "http://localhost:8080"

# Project ID → local project path mapping
PROJECTS_ROOT = Path.home() / "projects"

# Strict project_id validation — prevents path traversal
_PROJECT_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")

# Set up logging
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE)),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("supervisor")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_project_path(project_id: str) -> str:
    """Look up project local_path from the API, fall back to ~/projects/{id}."""
    try:
        import urllib.request

        with urllib.request.urlopen(
            f"{API_BASE}/api/projects/{project_id}", timeout=5
        ) as resp:
            data = json.loads(resp.read())
            return data.get("path", str(PROJECTS_ROOT / project_id))
    except Exception:
        return str(PROJECTS_ROOT / project_id)


def _post_event(project_id: str, event_type: str, data: dict = None) -> None:
    """Post an event to the API for SSE broadcast."""
    try:
        import urllib.request

        payload = json.dumps({
            "project_id": project_id,
            "event": event_type,
            **(data or {}),
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{API_BASE}/api/events",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.warning("Failed to post event to API: %s", e)


def _execute_cpo_task(project_id: str, task_name: str) -> bool:
    """
    Run queue-worker-full-pass.sh to execute the pending CPO task.
    Runs in a subprocess. Returns True if execution completed successfully.
    """
    import subprocess

    script = (Path.home() / "projects" / "codex-project-orchestrator"
              / "scripts" / "queue-worker-full-pass.sh")

    if not script.exists():
        logger.error("queue-worker-full-pass.sh not found at %s", script)
        return False

    logger.info("Executing CPO task %s via queue-worker-full-pass.sh", task_name)

    proc = None
    try:
        proc = subprocess.Popen(
            ["bash", str(script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(script.parent.parent),
        )
        stdout, stderr = proc.communicate(timeout=1800)  # 30 minute timeout
        if proc.returncode == 0:
            logger.info("Task %s completed successfully", task_name)
            if stdout:
                logger.info("Output (last 500 chars): %s", stdout[-500:])
            return True
        else:
            logger.error("Task %s failed (exit %d)", task_name, proc.returncode)
            if stderr:
                logger.error("stderr: %s", stderr[-500:])
            return False
    except subprocess.TimeoutExpired:
        logger.error("Task %s timed out after 30 minutes", task_name)
        if proc:
            proc.kill()
            proc.wait()
        return False
    except Exception as e:
        logger.error("Task %s execution error: %s", task_name, e)
        if proc:
            proc.kill()
            proc.wait()
        return False


def _create_cpo_task(project_id: str, prompt_id: str, content: str) -> str:
    """Create a CPO task directory and return the task_id."""
    task_id = f"{project_id}-{prompt_id[:8]}"
    task_dir = QUEUE_ROOT / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    project_path = _get_project_path(project_id)
    thread_jsonl = DATA_ROOT / project_id / "thread.jsonl"

    # Write task.md with full objective and proper acceptance criteria
    task_md = f"""# Dashboard prompt — {project_id}

## Project path
{project_path}

## Objective
{content}

## Execution context
You are Claude Code running autonomously via the Paladin Control Plane
dashboard. The user submitted this prompt expecting it to be fully executed.
Read the project CLAUDE.md for full infrastructure context and available
subagents. Use subagents where appropriate.

When complete:

Write a summary of what was done to:
{thread_jsonl}
as a JSON entry: {{"id": "<uuid>", "timestamp": "<iso>", "type": "response",
"author": "supervisor", "project_id": "{project_id}",
"content": "<summary of what was accomplished>"}}
Append this as a single line to the file.
Exit cleanly.

## Constraints
- Follow project CLAUDE.md architecture invariants
- Do not make changes outside the project directory without explicit
  instruction in the objective above
- Write exactly one response entry to thread.jsonl when done

## Acceptance criteria
- The objective above has been fully executed
- A response entry has been written to thread.jsonl summarising
  what was accomplished
- All changes committed if the objective involved file modifications
"""
    (task_dir / "task.md").write_text(task_md, encoding="utf-8")

    # Write status.json
    status = {
        "task_id": task_id,
        "project_id": project_id,
        "prompt_id": prompt_id,
        "status": "pending",
        "created": _now_iso(),
    }
    (task_dir / "status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )

    return task_id


def process_prompt(project_id: str, prompt: dict) -> None:
    """Process a single unhandled prompt."""
    prompt_id = prompt["id"]
    content = prompt["content"]

    logger.info("Processing prompt %s for project %s", prompt_id[:8], project_id)

    # Write routing response to thread
    add_thread_entry(
        project_id,
        "event",
        "system",
        "Supervisor received: routing to CPO...",
    )

    # Create CPO task first, then mark handled (so prompt isn't lost on failure)
    task_id = _create_cpo_task(project_id, prompt_id, content)
    mark_prompt_handled(project_id, prompt_id)
    logger.info("Created CPO task %s for prompt %s", task_id, prompt_id[:8])

    # Post event to API
    _post_event(project_id, "prompt_routed", {
        "prompt_id": prompt_id,
        "task_id": task_id,
    })

    logger.info("Routed prompt %s → task %s", prompt_id[:8], task_id)

    # Execute the task automatically
    success = _execute_cpo_task(project_id, task_id)
    if success:
        add_thread_entry(
            project_id, "event", "system",
            f"Task {task_id} completed successfully",
        )
        _post_event(project_id, "task_completed", {"task": task_id})
    else:
        add_thread_entry(
            project_id, "event", "system",
            f"Task {task_id} failed or timed out — check CPO logs",
        )
        _post_event(project_id, "task_failed", {"task": task_id})


def poll_once() -> int:
    """Scan all project prompt queues. Returns count of prompts processed."""
    count = 0
    if not DATA_ROOT.exists():
        return count

    for project_dir in sorted(DATA_ROOT.iterdir()):
        if not project_dir.is_dir():
            continue

        project_id = project_dir.name
        if not _PROJECT_ID_RE.match(project_id):
            logger.warning("Skipping invalid project_id: %s", project_id)
            continue
        try:
            prompts = get_prompt_queue(project_id)
            for prompt in prompts:
                try:
                    process_prompt(project_id, prompt)
                    count += 1
                except Exception as e:
                    logger.error(
                        "Error processing prompt %s for %s: %s",
                        prompt.get("id", "?")[:8],
                        project_id,
                        e,
                    )
        except Exception as e:
            logger.error("Error reading queue for %s: %s", project_id, e)

    return count


def main() -> None:
    """Main loop: write PID, poll forever."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()) + "\n")
    logger.info("Supervisor started (PID %d)", os.getpid())

    try:
        while True:
            count = poll_once()
            if count > 0:
                logger.info("Poll cycle complete: processed %d prompt(s)", count)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Supervisor stopped by signal")
    finally:
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
