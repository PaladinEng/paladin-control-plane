#!/usr/bin/env python3
"""
Paladin overnight meta-supervisor.
Runs once nightly via systemd timer.
Reads WORKQUEUE-MASTER.md, finds overnight-ready P1 tasks,
creates and executes CPO tasks for each, respects blast radius.
"""

import json
import logging
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

_PROJECT_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
WORKQUEUE_MASTER = Path.home() / "projects" / "WORKQUEUE-MASTER.md"
CPO_PENDING = Path.home() / "dev" / "queue" / "pending"
CPO_SCRIPT = (Path.home() / "projects" / "codex-project-orchestrator"
              / "scripts" / "queue-worker-full-pass.sh")
NOTIFY_FILE = Path.home() / "projects" / "NOTIFY.md"
DATA_ROOT = Path.home() / "paladin-control" / "data" / "projects"
LOG_DIR = Path.home() / "projects" / "paladin-control-plane" / "logs"


def notify(message: str) -> None:
    """Write to NOTIFY.md and send ntfy notification."""
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(NOTIFY_FILE, "a") as f:
        f.write(f"\n[{timestamp}] OVERNIGHT: {message}\n")
    try:
        subprocess.run([
            "curl", "-s", "-X", "POST",
            "http://localhost:8090/paladin-alerts",
            "-H", f"Title: Overnight — {message[:50]}",
            "-H", "Priority: default",
            "-H", "Tags: moon",
            "-d", message,
        ], timeout=5, capture_output=True)
    except Exception:
        pass


def parse_overnight_tasks() -> list[dict]:
    """
    Parse WORKQUEUE-MASTER.md for P1 tasks marked overnight-ready: YES
    and blast-radius: LOW or NONE.
    Returns list of task dicts.
    """
    if not WORKQUEUE_MASTER.exists():
        logger.error("WORKQUEUE-MASTER.md not found")
        return []

    content = WORKQUEUE_MASTER.read_text(encoding="utf-8")
    tasks = []

    # Find P1 section
    p1_match = re.search(
        r"##\s+P1[^\n]*\n(.*?)(?=\n##\s+P2|\n##\s+Blocked|\n##\s+Completed|\Z)",
        content, re.DOTALL,
    )
    if not p1_match:
        logger.info("No P1 section found in WORKQUEUE-MASTER.md")
        return []

    p1_section = p1_match.group(1)

    # Parse individual tasks (### headers)
    task_blocks = re.split(r"\n###\s+", p1_section)
    for block in task_blocks:
        if not block.strip():
            continue

        lines = block.strip().splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:])

        # Extract fields
        overnight = re.search(r"overnight-ready:\s*(.+)", body)
        blast = re.search(r"blast-radius:\s*(.+)", body)
        project = re.search(r"project:\s*(.+)", body)

        overnight_ready = overnight and "YES" in overnight.group(1).upper()
        blast_radius = blast.group(1).strip().split()[0] if blast else ""
        project_id = project.group(1).strip() if project else ""

        if not overnight_ready:
            continue
        if not blast_radius:
            logger.warning(
                "Skipping %s: blast-radius field missing, treating as unsafe",
                title,
            )
            continue
        if blast_radius.upper() not in ("NONE", "LOW"):
            logger.info(
                "Skipping %s: blast-radius %s requires manual approval",
                title, blast_radius,
            )
            notify(
                f"Task '{title}' skipped overnight: "
                f"blast-radius {blast_radius} requires your approval"
            )
            continue

        if project_id and not _PROJECT_ID_RE.match(project_id):
            logger.warning("Skipping %s: invalid project_id '%s'", title, project_id)
            continue

        tasks.append({
            "title": title,
            "project_id": project_id,
            "blast_radius": blast_radius,
            "body": body,
        })

    return tasks


def create_cpo_task(task: dict) -> Path:
    """Create a CPO task directory for an overnight task."""
    task_id = f"{task['project_id']}-overnight-{uuid.uuid4().hex[:8]}"
    task_dir = CPO_PENDING / task_id
    task_dir.mkdir(parents=True)

    project_path = (
        Path.home() / "projects" / task["project_id"]
        if task["project_id"] else Path.home() / "projects"
    )

    thread_jsonl = (
        DATA_ROOT / task["project_id"] / "thread.jsonl"
        if task["project_id"] else DATA_ROOT / "system" / "thread.jsonl"
    )

    task_md = f"""# Overnight task — {task['title']}

## Project path
{project_path}

## Objective
Execute this overnight task: {task['title']}

Task details from WORKQUEUE-MASTER.md:
{task['body']}

## Execution context
You are Claude Code running as part of the Paladin overnight automation.
This task was queued as overnight-ready with blast-radius: {task['blast_radius']}.
Read the project CLAUDE.md for full infrastructure context and available subagents.

When complete:
1. Update the project WORKQUEUE.md: mark this task complete with today's date
2. Update context/STATUS.md with current state
3. Commit all changes
4. Write a summary to {thread_jsonl} as a response entry
5. Exit cleanly.

## Constraints
- blast-radius is {task['blast_radius']} — proceed autonomously
- If anything unexpected arises that raises blast-radius, STOP and
  write to ~/projects/NOTIFY.md then exit
- Do not proceed with any operation not described in the objective
- Do NOT restart paladin-supervisor.service during execution.
  Send SIGHUP if a reload is needed:
  systemctl --user kill --signal=SIGHUP paladin-supervisor.service

## Acceptance criteria
- Task fully executed per the objective
- WORKQUEUE.md updated
- Changes committed
- Response written to thread.jsonl

When all work above is complete, you MUST exit immediately by
stopping all activity. Do not wait for further input.
"""

    (task_dir / "task.md").write_text(task_md)
    (task_dir / "status.json").write_text(json.dumps({
        "project_name": task_id,
        "state": "pending",
        "started_at": "",
        "execution_started_at": "",
        "handoff_ready_at": "",
        "finished_at": "",
        "log_file": "",
        "project_path": str(project_path),
        "outcome": "",
    }, indent=2))

    return task_dir


def run_task(task_dir: Path) -> bool:
    """Execute a CPO task. Returns True on success."""
    proc = None
    try:
        proc = subprocess.Popen(
            ["bash", str(CPO_SCRIPT)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(CPO_SCRIPT.parent.parent),
        )
        stdout, stderr = proc.communicate(timeout=1800)
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        logger.error("Task timed out: %s", task_dir.name)
        if proc:
            proc.kill()
            proc.wait()
        return False
    except Exception as e:
        logger.error("Task execution error: %s", e)
        if proc:
            proc.kill()
            proc.wait()
        return False


def main():
    logger.info("Overnight supervisor starting")
    notify("Overnight run started")

    tasks = parse_overnight_tasks()
    if not tasks:
        logger.info("No overnight-ready P1 tasks found")
        notify("Overnight run complete — no tasks to execute")
        return

    logger.info(
        "Found %d overnight-ready task(s): %s",
        len(tasks), [t["title"] for t in tasks],
    )

    completed = []
    failed = []

    for task in tasks:
        logger.info("Starting task: %s", task["title"])
        task_dir = create_cpo_task(task)

        success = run_task(task_dir)
        if success:
            completed.append(task["title"])
            logger.info("Completed: %s", task["title"])
        else:
            failed.append(task["title"])
            logger.error("Failed: %s", task["title"])

    summary = (
        f"Overnight complete. "
        f"Done: {len(completed)}, Failed: {len(failed)}. "
        f"Completed: {', '.join(completed) or 'none'}. "
        f"Failed: {', '.join(failed) or 'none'}."
    )
    logger.info(summary)
    notify(summary)


if __name__ == "__main__":
    main()
