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
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path so we can import backend modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.thread_service import (
    _read_full_queue,
    _write_queue,
    add_needs_input_request,
    add_thread_entry,
    get_prompt_queue,
    mark_prompt_handled,
)
import yaml as _yaml

# Hang detection constants
HANG_TIMEOUT_SECONDS = 10 * 60  # 10 minutes — timeout wrapper handles 30min hard cap
HANG_CHECK_INTERVAL = 60  # check every 60 seconds

# Retry cooldown for hang detector — prevents infinite retry loops
_retry_counts: dict[str, int] = {}  # project_id -> retry count
_retry_delays = [0, 60, 120, 300, 600]  # seconds between retries (exponential backoff)
_last_retry_time: dict[str, float] = {}  # project_id -> last retry timestamp

# Configuration
from backend.config import DATA_ROOT
QUEUE_ROOT = Path.home() / "dev" / "queue" / "pending"
POLL_INTERVAL = 30  # seconds
PID_FILE = Path.home() / "paladin-control" / "supervisor.pid"
LOG_FILE = PROJECT_ROOT / "logs" / "supervisor.log"
API_BASE = "http://localhost:8080"

# Project ID → local project path mapping
CPO_ACTIVE = Path.home() / "dev" / "queue" / "active"
PROJECTS_ROOT = Path.home() / "projects"

# Strict project_id validation — prevents path traversal
_PROJECT_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")

# Active blocker registry — in-memory, rebuilt from disk on restart
# Format: {blocker_id: {type, fingerprint, project_id, task_name,
#                       created_at, attempts, status, blocker_data}}
_active_blockers: dict[str, dict] = {}
_blocker_id_counter = 0

PATTERNS_DIR = Path.home() / "projects" / "paladin-context-system" / "patterns"
PATTERNS_REGISTRY = PATTERNS_DIR / "_registry.yaml"

MAX_RETRIES = 5


def _load_patterns_registry() -> dict:
    """Load the blocker patterns registry from disk."""
    try:
        if PATTERNS_REGISTRY.exists():
            return _yaml.safe_load(PATTERNS_REGISTRY.read_text()) or {}
    except Exception as e:
        logger.warning(f"Failed to load patterns registry: {e}")
    return {}


def _new_blocker_id() -> str:
    global _blocker_id_counter
    _blocker_id_counter += 1
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"blocker-{ts}-{_blocker_id_counter:03d}"


# Set up logging
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE)),
    ],
)
logger = logging.getLogger("supervisor")


def _reload_handler(signum, frame):
    """Handle SIGHUP — log reload signal, continue running.

    Tasks that modify poll_prompts.py should send SIGHUP instead of
    restarting the service. The updated code takes effect on next
    full service restart (e.g. after reboot or manual restart).
    Running tasks are not interrupted.
    """
    logger.info(
        "SIGHUP received — supervisor continuing without restart. "
        "Code changes to poll_prompts.py take effect on next full restart."
    )


signal.signal(signal.SIGHUP, _reload_handler)


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


def notify(
    project_id: str,
    content: str,
    entry_type: str = "event",
    ntfy_title: str = None,
    ntfy_priority: str = "default",
    ntfy_tags: str = "bell",
    ntfy_topic: str = "paladin-alerts",
) -> None:
    """
    Unified notification — writes to project thread AND sends ntfy push.

    entry_type: "event" for task events, "system" for system messages,
                "response" for supervisor responses
    ntfy_priority: min, low, default, high, urgent
    ntfy_tags: comma-separated ntfy tag names (emoji shortcuts)
    """
    # 1. Write to project thread
    try:
        thread_file = DATA_ROOT / project_id / "thread.jsonl"
        thread_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": entry_type,
            "author": "system",
            "project_id": project_id,
            "content": content,
        }
        with open(thread_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning("Failed to write thread entry: %s", e)

    # 2. Send ntfy push notification
    try:
        title = ntfy_title or f"[{project_id}] {content[:60]}"
        subprocess.run(
            [
                "curl", "-s", "-X", "POST",
                f"http://localhost:8090/{ntfy_topic}",
                "-H", f"Title: {title}",
                "-H", f"Priority: {ntfy_priority}",
                "-H", f"Tags: {ntfy_tags}",
                "-H", f"Click: https://dashboard.paladinrobotics.com/#/project/{project_id}",
                "-d", content,
            ],
            timeout=5,
            capture_output=True,
        )
    except Exception as e:
        logger.warning("Failed to send ntfy notification: %s", e)

    # 3. Broadcast SSE event so dashboard updates in real time
    _post_event(project_id, "thread_update", {})


def _should_retry_now(prompt_key: str) -> bool:
    """Return True if enough time has passed since last retry for this prompt."""
    count = _retry_counts.get(prompt_key, 0)
    if count >= len(_retry_delays):
        logger.warning("Prompt %s has failed %d times — giving up", prompt_key, count)
        return False
    delay = _retry_delays[count]
    last = _last_retry_time.get(prompt_key, 0)
    if time.time() - last < delay:
        return False
    return True


def _record_retry(prompt_key: str) -> None:
    """Record a retry attempt for exponential backoff tracking."""
    _retry_counts[prompt_key] = _retry_counts.get(prompt_key, 0) + 1
    _last_retry_time[prompt_key] = time.time()
    next_delay = _retry_delays[min(_retry_counts[prompt_key], len(_retry_delays) - 1)]
    logger.info(
        "Prompt %s retry #%d (next delay: %ds)",
        prompt_key, _retry_counts[prompt_key], next_delay,
    )


def _get_active_task_mtime(task_dir: Path) -> float:
    """Return most recent mtime of any file in the task directory."""
    try:
        mtimes = [
            f.stat().st_mtime
            for f in task_dir.rglob("*")
            if f.is_file()
        ]
        return max(mtimes) if mtimes else task_dir.stat().st_mtime
    except Exception:
        return 0.0


def _task_completed_work(task_dir: Path, project_path: str) -> bool:
    """
    Check if a task completed its work before hanging.
    Returns True if a git commit was made in project_path
    after the task directory was created.
    """
    try:
        task_created = task_dir.stat().st_mtime
        result = subprocess.run(
            ["git", "log", "--format=%ct", "-1"],
            capture_output=True, text=True,
            cwd=project_path, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return False
        last_commit_time = float(result.stdout.strip())
        return last_commit_time > task_created
    except Exception:
        return False


def _parse_project_path_from_task(task_md_path: Path) -> str | None:
    """Extract project path from a task.md file (## Project path section)."""
    try:
        lines = task_md_path.read_text(encoding="utf-8").splitlines()
        in_section = False
        for line in lines:
            if line.strip() == "## Project path":
                in_section = True
                continue
            if in_section:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    return stripped
                if stripped.startswith("#"):
                    break  # hit next section
        return None
    except Exception:
        return None


def hang_detector(cpo_active_dir: Path) -> None:
    """
    Background thread: watches active/ for tasks with no recent file
    activity. If a task directory has had no file changes for
    HANG_TIMEOUT_SECONDS, kills any claude processes and moves the
    task to failed.
    """
    while True:
        time.sleep(HANG_CHECK_INTERVAL)
        try:
            if not cpo_active_dir.exists():
                continue
            for task_dir in cpo_active_dir.iterdir():
                if not task_dir.is_dir():
                    continue

                mtime = _get_active_task_mtime(task_dir)
                age = time.time() - mtime

                if age > HANG_TIMEOUT_SECONDS:
                    project_id = task_dir.name.rsplit("-", 1)[0]
                    logger.warning(
                        "Hang detected: %s has had no file activity for %.0f minutes",
                        task_dir.name, age / 60,
                    )

                    # Kill any running claude processes
                    try:
                        subprocess.run(
                            ["pkill", "-f", "claude.*--print"],
                            capture_output=True,
                        )
                        logger.info("Killed hung claude process(es)")
                    except Exception as e:
                        logger.warning("pkill failed: %s", e)

                    # Move task to failed
                    failed_dir = cpo_active_dir.parent / "failed" / task_dir.name
                    failed_dir.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        task_dir.rename(failed_dir)
                        logger.info("Moved hung task to failed/: %s", task_dir.name)
                    except Exception as e:
                        logger.error("Failed to move task: %s", e)

                    # Check if work actually completed before hang
                    project_path = None
                    task_md = failed_dir / "task.md"
                    if task_md.exists():
                        project_path = _parse_project_path_from_task(task_md)

                    work_done = False
                    if project_path:
                        work_done = _task_completed_work(failed_dir, project_path)

                    if work_done:
                        logger.info(
                            "Hung task %s had completed its work — "
                            "marking prompt as handled to prevent retry",
                            task_dir.name,
                        )
                        # Mark the prompt as handled so supervisor doesn't retry
                        try:
                            queue = _read_full_queue(project_id)
                            prompt_id_suffix = task_dir.name.split("-")[-1]
                            for entry in queue:
                                eid = entry.get("id", "")
                                if eid.startswith(prompt_id_suffix) or \
                                   eid.endswith(prompt_id_suffix):
                                    entry["handled"] = True
                                    logger.info("Marked prompt %s as handled", eid)
                                    break
                            _write_queue(project_id, queue)

                            add_thread_entry(
                                project_id, "event", "system",
                                f"Task {task_dir.name} completed work but hung on "
                                f"exit. Auto-killed after {age / 60:.0f} minutes. "
                                f"Work committed — no retry needed.",
                            )
                        except Exception as e:
                            logger.error("Failed to mark prompt handled: %s", e)

                        notify(
                            project_id,
                            f"Task {task_dir.name} hung after completing work. "
                            f"Killed and marked complete — no retry.",
                            ntfy_title=f"\u26a0\ufe0f [{project_id}] Hung task — work was done",
                            ntfy_tags="warning",
                            ntfy_priority="default",
                        )
                    else:
                        # Retry cooldown — prevent infinite retry loops
                        prompt_key = task_dir.name  # project_id-prompt_id[:8]
                        if _should_retry_now(prompt_key):
                            _record_retry(prompt_key)
                            logger.info(
                                "Hung task %s had NOT completed work — "
                                "leaving prompt unhandled for retry "
                                "(attempt #%d)",
                                task_dir.name,
                                _retry_counts.get(prompt_key, 0),
                            )
                            notify(
                                project_id,
                                f"Task {task_dir.name} was killed after "
                                f"{age / 60:.0f} minutes with no file activity. "
                                f"No work detected — will retry "
                                f"(attempt #{_retry_counts.get(prompt_key, 0)}).",
                                ntfy_title=f"\U0001f534 [{project_id}] Hung task killed — retrying",
                                ntfy_tags="skull",
                                ntfy_priority="high",
                            )
                        else:
                            # Max retries exceeded — mark handled and give up
                            retry_count = _retry_counts.get(prompt_key, 0)
                            logger.warning(
                                "Hung task %s — max retries (%d) exceeded, "
                                "marking as handled",
                                task_dir.name, retry_count,
                            )
                            try:
                                queue = _read_full_queue(project_id)
                                prompt_id_suffix = task_dir.name.split("-")[-1]
                                for entry in queue:
                                    eid = entry.get("id", "")
                                    if eid.startswith(prompt_id_suffix) or \
                                       eid.endswith(prompt_id_suffix):
                                        entry["handled"] = True
                                        logger.info(
                                            "Marked prompt %s as handled "
                                            "(max retries exceeded)", eid,
                                        )
                                        break
                                _write_queue(project_id, queue)
                            except Exception as e:
                                logger.error(
                                    "Failed to mark prompt handled: %s", e,
                                )
                            notify(
                                project_id,
                                f"Prompt {prompt_key} failed after "
                                f"{retry_count} retries. Check CPO logs "
                                f"and resubmit manually if needed.",
                                ntfy_title=f"\u274c [{project_id}] Max retries exceeded",
                                ntfy_tags="x",
                                ntfy_priority="high",
                            )
        except Exception as e:
            logger.error("Hang detector error: %s", e)


def start_hang_detector() -> None:
    """Start the hang detector as a daemon thread."""
    cpo_active = Path.home() / "dev" / "queue" / "active"
    t = threading.Thread(
        target=hang_detector,
        args=(cpo_active,),
        daemon=True,
        name="hang-detector",
    )
    t.start()
    logger.info("Hang detector thread started")


def _execute_cpo_task(project_id: str, task_name: str) -> str:
    """
    Run queue-worker-full-pass.sh to execute the pending CPO task.
    Returns "success", "failed", or "timeout".
    """
    script = (Path.home() / "projects" / "codex-project-orchestrator"
              / "scripts" / "queue-worker-full-pass.sh")

    if not script.exists():
        logger.error("queue-worker-full-pass.sh not found at %s", script)
        return "failed"

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
            return "success"
        else:
            logger.error("Task %s failed (exit %d)", task_name, proc.returncode)
            if stderr:
                logger.error("stderr: %s", stderr[-500:])
            return "failed"
    except subprocess.TimeoutExpired:
        logger.error("Task %s timed out after 30 minutes", task_name)
        if proc:
            proc.kill()
            proc.wait()
        return "timeout"
    except Exception as e:
        logger.error("Task %s execution error: %s", task_name, e)
        if proc:
            proc.kill()
            proc.wait()
        return "failed"


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
- Do NOT run systemctl restart paladin-supervisor.service or
  systemctl stop paladin-supervisor.service during task execution.
  The supervisor manages its own restart lifecycle and restarting
  it mid-queue disrupts in-flight state and resets the hang detector.
  If poll_prompts.py was modified and a reload is needed, use:
  systemctl --user kill --signal=SIGHUP paladin-supervisor.service
  This keeps the supervisor running without disrupting the queue.
- Do NOT restart paladin-api.service unless the task explicitly
  requires it for new endpoints to take effect. If restart is
  needed, do it as the final step after all other work is committed.

## Acceptance criteria
- The objective above has been fully executed
- A response entry has been written to thread.jsonl summarising
  what was accomplished
- All changes committed if the objective involved file modifications

When all work above is complete, you MUST exit immediately by
stopping all activity. Do not wait for further input.
Also run this command as the very last action before exiting:
  touch /tmp/paladin-cpo-done-{task_id}
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


def _active_queue_is_empty() -> bool:
    """Return True if no tasks are currently executing."""
    try:
        return not any(CPO_ACTIVE.iterdir())
    except Exception:
        return True


def _cleanup_orphaned_pending() -> int:
    """Scan pending/ for task files whose prompt is already handled.

    This catches orphans left by the old premature-handling bug: the prompt
    was marked handled at task-creation time, so the supervisor never picked
    the task file back up.  Move each orphan to completed/ with a cleanup note.

    Returns the number of tasks cleaned up.
    """
    cleaned = 0
    completed_dir = QUEUE_ROOT.parent / "completed"
    try:
        if not QUEUE_ROOT.exists():
            return 0
        for task_dir in QUEUE_ROOT.iterdir():
            if not task_dir.is_dir():
                continue
            status_file = task_dir / "status.json"
            if not status_file.exists():
                continue
            try:
                status = json.loads(status_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            project_id = status.get("project_id")
            prompt_id = status.get("prompt_id")
            if not project_id or not prompt_id:
                continue
            # Check if the prompt is already handled
            try:
                queue = _read_full_queue(project_id)
            except Exception:
                continue
            prompt_handled = False
            for entry in queue:
                if entry.get("id") == prompt_id and entry.get("handled"):
                    prompt_handled = True
                    break
            if not prompt_handled:
                continue
            # Prompt is handled but task is still in pending — orphan
            logger.warning(
                "Orphaned pending task %s: prompt %s already handled — "
                "moving to completed/",
                task_dir.name, prompt_id[:8],
            )
            # Write cleanup note
            note = (
                f"Cleaned up by supervisor at {_now_iso()}. "
                f"Prompt {prompt_id} was already marked handled "
                f"(likely premature handling bug). Task never executed."
            )
            (task_dir / "cleanup-note.txt").write_text(note, encoding="utf-8")
            # Move to completed/
            dest = completed_dir / task_dir.name
            completed_dir.mkdir(parents=True, exist_ok=True)
            try:
                task_dir.rename(dest)
                cleaned += 1
            except Exception as e:
                logger.error("Failed to move orphaned task %s: %s", task_dir.name, e)
    except Exception as e:
        logger.error("Orphaned pending cleanup error: %s", e)
    return cleaned


def handle_blocker(project_id: str, blocker: dict, task_name: str) -> None:
    """
    Handle a detected blocker:
    1. Check if same fingerprint is already active
    2. Attempt autonomous resolution if pattern says auto_fix: true
    3. If unresolved, register as active blocker and send needs-input
    4. Update patterns registry encountered_by list
    """
    blocker_type = blocker.get("type", "unknown")
    fingerprint = blocker.get("fingerprint", f"{blocker_type}-{project_id}")

    # Check if same blocker already active
    for bid, active in _active_blockers.items():
        if active["fingerprint"] == fingerprint and active["status"] == "active":
            logger.info(
                f"Blocker {fingerprint} already active as {bid} — "
                f"parking task without new notification"
            )
            _park_prompt(project_id, blocker_type, bid)
            return

    # Load patterns registry to check auto_fix
    registry = _load_patterns_registry()
    pattern = registry.get("patterns", {}).get(blocker_type, {})
    auto_fix = pattern.get("auto_fix", False)

    # Attempt autonomous resolution
    if auto_fix:
        resolved = _attempt_autonomous_fix(blocker_type, blocker, project_id)
        if resolved:
            logger.info(f"Autonomous fix succeeded for {blocker_type}")
            notify(
                project_id,
                f"Blocker {blocker_type} resolved autonomously. Task will retry.",
                ntfy_title=f"\U0001f527 [{project_id}] Blocker auto-fixed",
                ntfy_tags="wrench",
                ntfy_priority="low",
            )
            return

    # Register active blocker
    blocker_id = _new_blocker_id()
    _active_blockers[blocker_id] = {
        "type": blocker_type,
        "fingerprint": fingerprint,
        "project_id": project_id,
        "task_name": task_name,
        "created_at": time.time(),
        "attempts": 1,
        "status": "active",
        "blocker_data": blocker,
    }

    # Update patterns registry encountered_by
    _update_registry_encountered_by(blocker_type, project_id)

    # Send needs-input to dashboard
    _send_blocker_needs_input(project_id, blocker_id, blocker, task_name)

    logger.info(
        f"Blocker {blocker_id} registered: {blocker_type} in {project_id}"
    )


def _attempt_autonomous_fix(
    blocker_type: str, blocker: dict, project_id: str
) -> bool:
    """
    Attempt to fix a blocker autonomously based on known fix steps.
    Returns True if resolved, False if escalation needed.
    """
    logger.info(f"Attempting autonomous fix for {blocker_type}")

    fixes = {
        "github-auth": [
            ["gh", "auth", "refresh"],
        ],
        "api-down": [
            ["systemctl", "--user", "restart", "paladin-api.service"],
        ],
        "missing-credential": [
            ["bash", "-c", "source ~/.paladin-secrets/tokens"],
        ],
        "path-issue": [
            ["bash", "-c",
             "export PATH=$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"],
        ],
        "missing-dependency": [],  # Handled in task template
        "service-crash": [
            ["systemctl", "--user", "restart", "paladin-api.service"],
        ],
        "disk-full": [
            ["bash", "-c",
             "find ~/dev/queue/completed -mtime +7 -exec rm -rf {} + 2>/dev/null; "
             "find ~/dev/logs -mtime +7 -delete 2>/dev/null"],
        ],
        "trust-prompt": [],  # Cannot fix autonomously
    }

    steps = fixes.get(blocker_type, [])
    if not steps:
        return False

    for step in steps:
        try:
            result = subprocess.run(
                step, capture_output=True, text=True, timeout=30
            )
            logger.info(f"Auto-fix step {step}: exit {result.returncode}")
        except Exception as e:
            logger.warning(f"Auto-fix step failed: {e}")

    # Verify fix worked (simple check)
    if blocker_type == "api-down":
        import urllib.request
        try:
            urllib.request.urlopen(
                "http://localhost:8080/health", timeout=5
            )
            return True
        except Exception:
            return False

    if blocker_type == "github-auth":
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0

    # For other types, assume fix worked if no exception
    return len(steps) > 0


def _park_prompt(project_id: str, blocker_type: str, blocker_id: str) -> None:
    """Mark unhandled prompts in this project as parked for this blocker."""
    queue = _read_full_queue(project_id)
    parked_count = 0
    for entry in queue:
        if not entry.get("handled") and not entry.get("parked"):
            entry["parked"] = True
            entry["parked_reason"] = blocker_type
            entry["parked_blocker_id"] = blocker_id
            entry["parked_at"] = time.time()
            parked_count += 1
    if parked_count:
        _write_queue(project_id, queue)
        logger.info(
            f"Parked {parked_count} prompts in {project_id} "
            f"for blocker {blocker_id}"
        )


def _send_blocker_needs_input(
    project_id: str, blocker_id: str, blocker: dict, task_name: str
) -> None:
    """Send a structured needs-input entry for a blocker."""
    blocker_type = blocker.get("type", "unknown")
    description = blocker.get("description", "Unknown error")
    fix_instructions = blocker.get("fix_instructions", "Check CPO logs.")
    completed = blocker.get("completed_steps", [])
    remaining = blocker.get("remaining_steps", [])

    completed_text = (
        "\n".join(f"  \u2705 {s}" for s in completed) if completed else "  (none)"
    )
    remaining_text = (
        "\n".join(f"  \u23f3 {s}" for s in remaining) if remaining else "  (unknown)"
    )

    question = (
        f"\u23f8\ufe0f Task blocked: {blocker_type}\n\n"
        f"What happened: {description}\n\n"
        f"Completed before blocker:\n{completed_text}\n\n"
        f"Still to do:\n{remaining_text}\n\n"
        f"To fix:\n{fix_instructions}\n\n"
        f"When done, reply 'cleared' and this task will resume automatically.\n"
        f"Blocker ID: {blocker_id}"
    )

    add_needs_input_request(project_id, question, blocker_id)

    # Also send ntfy
    notify(
        project_id,
        f"Blocker: {blocker_type} \u2014 {description[:80]}",
        ntfy_title=f"\u23f8\ufe0f [{project_id}] Task blocked",
        ntfy_tags="pause_button",
        ntfy_priority="high",
        ntfy_topic="paladin-alerts",
    )


def _update_registry_encountered_by(blocker_type: str, project_id: str) -> None:
    """Update the patterns registry to record this project encountered this blocker."""
    try:
        if not PATTERNS_REGISTRY.exists():
            return
        registry = _yaml.safe_load(PATTERNS_REGISTRY.read_text()) or {}
        patterns = registry.get("patterns", {})
        if blocker_type in patterns:
            encountered = patterns[blocker_type].get("encountered_by", [])
            if project_id not in encountered:
                encountered.append(project_id)
                patterns[blocker_type]["encountered_by"] = encountered
                registry["patterns"] = patterns
                import datetime as _dt
                registry["last_updated"] = _dt.date.today().isoformat()
                PATTERNS_REGISTRY.write_text(
                    _yaml.dump(registry, default_flow_style=False)
                )
    except Exception as e:
        logger.warning(f"Failed to update registry encountered_by: {e}")


def _get_retry_count(prompt_id: str) -> int:
    """Count how many times this prompt has been attempted."""
    cpo_root = Path.home() / "dev" / "queue"
    count = 0
    for subdir in ["completed", "failed"]:
        try:
            for task_dir in (cpo_root / subdir).iterdir():
                if task_dir.name.endswith(prompt_id[:8]):
                    count += 1
        except FileNotFoundError:
            continue
    return count


def _should_give_up(project_id: str, prompt_id: str) -> bool:
    """Return True if prompt has exceeded retry limit."""
    count = _get_retry_count(prompt_id)
    if count >= MAX_RETRIES:
        logger.warning(
            f"Prompt {prompt_id[:8]} has failed {count} times \u2014 giving up"
        )
        notify(
            project_id,
            f"Prompt {prompt_id[:8]} failed after {count} attempts. "
            f"Marking as handled. Resubmit manually if needed.",
            ntfy_title=f"\u274c [{project_id}] Max retries exceeded",
            ntfy_tags="x",
            ntfy_priority="high",
        )
        return True
    return False


def process_prompt(project_id: str, prompt: dict) -> bool:
    """Process a single unhandled prompt. Returns True if executed, False if deferred."""
    prompt_id = prompt["id"]
    content = prompt["content"]

    logger.info("Processing prompt %s for project %s", prompt_id[:8], project_id)

    # Check retry limits before proceeding
    if _should_give_up(project_id, prompt_id):
        mark_prompt_handled(project_id, prompt_id)
        return True

    # Check active/ before executing — defer if busy
    if not _active_queue_is_empty():
        logger.info(
            "Active queue not empty — deferring prompt %s to next poll cycle",
            prompt_id[:8],
        )
        return False

    # Create CPO task
    task_id = _create_cpo_task(project_id, prompt_id, content)
    logger.info("Created CPO task %s for prompt %s", task_id, prompt_id[:8])

    # Unified notification: task routed
    notify(
        project_id,
        f"Task {task_id} created and queued for execution",
        ntfy_tags="gear",
        ntfy_priority="low",
    )

    logger.info("Routed prompt %s → task %s", prompt_id[:8], task_id)

    # Execute the task — prompt is only marked handled on success or
    # by the hang detector when work was committed. This ensures failed
    # or hung tasks that did no work can be retried.
    result = _execute_cpo_task(project_id, task_id)

    if result == "success":
        mark_prompt_handled(project_id, prompt_id)
        notify(
            project_id,
            f"Task {task_id} completed successfully",
            ntfy_title=f"\u2705 [{project_id}] Task complete",
            ntfy_tags="white_check_mark",
            ntfy_priority="default",
        )
    elif result == "timeout":
        # Don't mark handled — hang detector will decide based on
        # whether work was committed
        notify(
            project_id,
            f"Task {task_id} timed out after 30 minutes. "
            f"Claude Code may have hung. Check ~/dev/queue/active/ "
            f"and kill any stuck processes.",
            ntfy_title=f"\u23f1 [{project_id}] Task timed out",
            ntfy_tags="timer_clock",
            ntfy_priority="high",
        )
    else:
        # Don't mark handled — leave for retry on next poll cycle
        notify(
            project_id,
            f"Task {task_id} failed \u2014 check CPO logs",
            ntfy_title=f"\u274c [{project_id}] Task failed",
            ntfy_tags="x",
            ntfy_priority="high",
        )
    return True


def poll_once() -> int:
    """Scan all project prompt queues. Process at most ONE prompt per cycle.
    Returns count of prompts processed (0 or 1)."""
    if not DATA_ROOT.exists():
        return 0

    # Clean up orphaned pending tasks from premature handling
    cleaned = _cleanup_orphaned_pending()
    if cleaned > 0:
        logger.info("Cleaned up %d orphaned pending task(s)", cleaned)

    # Collect all unhandled prompts across all projects
    all_prompts: list[tuple[str, dict]] = []
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
                all_prompts.append((project_id, prompt))
        except Exception as e:
            logger.error("Error reading queue for %s: %s", project_id, e)

    if not all_prompts:
        return 0

    # Process only the FIRST prompt — leave the rest for subsequent cycles
    project_id, prompt = all_prompts[0]
    try:
        executed = process_prompt(project_id, prompt)
        if not executed:
            # Deferred due to active queue — log remaining depth
            logger.info("Queue depth: %d prompt(s) waiting", len(all_prompts))
            return 0
    except Exception as e:
        logger.error(
            "Error processing prompt %s for %s: %s",
            prompt.get("id", "?")[:8],
            project_id,
            e,
        )
        return 0

    # Log remaining queue depth
    remaining = len(all_prompts) - 1
    if remaining > 0:
        logger.info("Queue depth: %d prompt(s) waiting", remaining)

    return 1


def main() -> None:
    """Main loop: write PID, poll forever."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()) + "\n")
    logger.info("Supervisor started (PID %d)", os.getpid())

    start_hang_detector()

    cycle_count = 0
    try:
        while True:
            cycle_count += 1
            logger.info(
                "Supervisor heartbeat — poll cycle %d (PID %d)",
                cycle_count,
                os.getpid(),
            )
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
