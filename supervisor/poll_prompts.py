"""
Meta-supervisor prompt handler.

Polls all project prompt queues for unhandled prompts and routes each one
to a CPO task directory for execution by queue-worker-full-pass.sh.

Runs as a systemd user service (paladin-supervisor.service).
"""

import json
import logging
import os
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
    """Resolve the local path for a project."""
    project_dir = PROJECTS_ROOT / project_id
    if project_dir.exists():
        return str(project_dir)
    return str(project_dir)


def _post_event(project_id: str, prompt_id: str, task_id: str) -> None:
    """Post a prompt_routed event to the API."""
    try:
        import urllib.request

        payload = json.dumps({
            "type": "prompt_routed",
            "project_id": project_id,
            "prompt_id": prompt_id,
            "task_id": task_id,
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


def _create_cpo_task(project_id: str, prompt_id: str, content: str) -> str:
    """Create a CPO task directory and return the task_id."""
    task_id = f"{project_id}-{prompt_id[:8]}"
    task_dir = QUEUE_ROOT / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    project_path = _get_project_path(project_id)
    data_path = DATA_ROOT / project_id

    # Write task.md
    task_md = f"""# Dashboard prompt — {project_id}

## Project path
{project_path}

## Objective
{content}

## Constraints
Follow project CLAUDE.md. Write response to
{data_path}/thread.jsonl
as a thread entry with type=response, author=supervisor.
Exit cleanly when done.

## Acceptance criteria
Response written to thread.jsonl
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

    # Mark as handled immediately to prevent double-processing
    mark_prompt_handled(project_id, prompt_id)

    # Write routing response to thread
    add_thread_entry(
        project_id,
        "event",
        "system",
        f"Supervisor received: routing to CPO...",
    )

    # Create CPO task
    task_id = _create_cpo_task(project_id, prompt_id, content)
    logger.info("Created CPO task %s for prompt %s", task_id, prompt_id[:8])

    # Post event to API
    _post_event(project_id, prompt_id, task_id)

    logger.info("Routed prompt %s → task %s", prompt_id[:8], task_id)


def poll_once() -> int:
    """Scan all project prompt queues. Returns count of prompts processed."""
    count = 0
    if not DATA_ROOT.exists():
        return count

    for project_dir in sorted(DATA_ROOT.iterdir()):
        if not project_dir.is_dir():
            continue

        project_id = project_dir.name
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
