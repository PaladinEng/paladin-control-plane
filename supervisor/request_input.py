#!/usr/bin/env python3
"""
Request input from the dashboard and wait for a response.

Usage:
  python3 request_input.py <project_id> <task_id> "<question>"

This script is called by Claude Code tasks via bash when they need input.
It posts a needs-input request to the API and polls for the response file.
Prints the response content to stdout on success, exits 1 on timeout.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DATA_ROOT = Path(
    os.environ.get("PALADIN_DATA_ROOT",
    str(Path.home() / "paladin-control" / "data" / "projects"))
)


def main():
    if len(sys.argv) < 4:
        print(
            "Usage: request_input.py <project_id> <task_id> <question>",
            file=sys.stderr,
        )
        sys.exit(1)

    project_id = sys.argv[1]
    task_id = sys.argv[2]
    question = sys.argv[3]
    api_base = "http://localhost:8080"
    max_wait = 8 * 3600  # 8 hours
    poll_interval = 30  # seconds

    # Post needs-input request
    payload = json.dumps({"question": question, "task_id": task_id}).encode()
    req = urllib.request.Request(
        f"{api_base}/api/projects/{project_id}/needs-input",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            entry = json.loads(resp.read())
            entry_id = entry["id"]
    except Exception as e:
        print(f"Failed to post needs-input: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Waiting for response to entry {entry_id}...", file=sys.stderr)

    # Poll for response file
    elapsed = 0
    response_file = DATA_ROOT / project_id / "responses" / f"{entry_id}.json"

    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        try:
            data = json.loads(response_file.read_text(encoding="utf-8"))
            print(data["response"])
            sys.exit(0)
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            pass

    print("Timeout: no response received after 8 hours", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
