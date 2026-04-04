# Paladin Control Plane

## Identity and purpose
Autonomous AI orchestration dashboard for Paladin Robotics. Provides a
web interface for monitoring projects, dispatching prompts to Claude Code
agents via CPO, and receiving mobile notifications via ntfy.

- **Public URL:** https://dashboard.paladinrobotics.com
- **Local URL:** http://10.1.10.50:8080
- **Owner:** Alwyn V. Smith III (Paladin Robotics)
- **Repo:** PaladinEng/paladin-control-plane (private)

## Architecture overview

All services run on um790pronode1 (10.1.10.50) as systemd user services.

| Component | Port | Service | Notes |
|-----------|------|---------|-------|
| FastAPI backend | 8080 | paladin-api.service | REST API + static file serving |
| Vanilla JS frontend | — | served from /static/ | No build tools, no npm |
| ntfy notifications | 8090 | ntfy.service (system) | Push to iOS/Android |
| Meta-supervisor | — | paladin-supervisor.service | Polls every 30s, sequential queue |
| Overnight timer | — | paladin-overnight.timer | Daily at 23:00 UTC |
| Cloudflare Tunnel | — | cloudflared.service (system) | dashboard.paladinrobotics.com |
| GitHub OAuth | — | via auth middleware | PaladinEng only, Tailscale bypass |

### Request flow
Dashboard prompt -> POST /api/projects/{id}/prompt -> prompt-queue.json
-> meta-supervisor (30s poll) -> CPO task in ~/dev/queue/pending/
-> queue-worker-full-pass.sh -> Claude Code execution -> thread.jsonl response

### Authentication
- **Public access:** GitHub OAuth (PaladinEng account only), 7-day session cookie
- **Tailscale access:** Direct IP bypass (10.1.10.x, 100.x.x.x), no auth required
- **Localhost:** 127.0.0.1 bypass for local testing
- Header spoofing prevention: trusts direct connection IP only, not X-Forwarded-For

## Key file locations

| Path | Purpose |
|------|---------|
| backend/ | FastAPI application (routes/, models/, services/) |
| frontend/ | Static web assets (index.html, css/, js/) |
| supervisor/ | Meta-supervisor (poll_prompts.py, overnight.py, request_input.py) |
| config/ | Systemd unit files |
| context/ | Project context files (STATUS.md, WORKQUEUE.md, etc.) |
| logs/ | Session logs, supervisor logs, overnight logs |
| ~/paladin-control/data/projects/{id}/ | Thread data (thread.jsonl) and prompt queues (prompt-queue.json) |
| ~/dev/queue/{pending,active,completed,failed}/ | CPO task queue directories |
| ~/dev/projects/codex-project-orchestrator/scripts/ | Queue runner scripts |
| .venv/ | Python 3.12+ virtual environment |

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | /health | Health check |
| GET | /auth/status | Auth state |
| GET/POST | /auth/login, /callback, /logout | OAuth flow |
| GET | /api/projects | List all projects |
| GET | /api/projects/{id} | Single project detail |
| GET | /api/events | SSE stream |
| POST | /api/events | Post event to SSE |
| GET | /api/projects/{id}/thread | Thread entries |
| POST | /api/projects/{id}/prompt | Submit prompt |
| POST | /api/projects/{id}/needs-input | Create needs-input entry |
| POST | /api/projects/{id}/respond | Submit response |
| POST | /api/projects/{id}/prompts/batch | Batch prompt submission |
| POST | /api/projects/{id}/prompts/upload | Upload .md/.txt file as prompts |
| POST | /api/projects/{id}/archive | Archive project |
| POST | /api/projects/{id}/restore | Restore project |
| GET | /api/projects/{id}/logs/{filename} | Download session log |
| POST | /api/projects/create | Create new project (4-mode) |
| POST | /api/projects/{id}/provisioning-complete | Mark project provisioned |
| POST | /api/projects/uploads | Upload brief file |
| GET | /api/system/config | System config (ignore list, compliance) |
| POST | /api/projects/{id}/workqueue/add | Add workqueue item |

## Available subagents

Defined in .claude/agents/:

- **api-developer** (Sonnet) — FastAPI routes, Python backend, systemd config, REST API design
- **frontend-developer** (Sonnet) — Vanilla JS/HTML/CSS, SSE, mobile-responsive UI
- **infra-integrator** (Sonnet) — Systemd services, cloudflared, ntfy, OAuth middleware

Pattern: Opus lead + Sonnet workers for parallel tasks.

## Session start checklist
1. Read context/STATUS.md and context/WORKQUEUE.md
2. Check ~/projects/WORKQUEUE-MASTER.md for cross-project PCP-* priorities
3. If ~/projects/tonight.md exists, read and follow it
4. Check ~/dev/queue/active/ for stuck tasks
5. Run service health check:
   ```
   systemctl --user status paladin-api paladin-supervisor 2>/dev/null
   curl -s localhost:8080/health
   ```

## Session end requirements (MANDATORY)
1. Verify services running: `systemctl --user status paladin-api`
2. Update context/STATUS.md with current state
3. Update context/WORKQUEUE.md — move completed items, add new ones
4. Update context/DECISIONS.md if architectural decisions were made
5. Commit ALL context file changes before exiting
6. Write session log to logs/session-YYYY-MM-DD-NNN.md
7. Print `FINISHED WORK` to console

### Session log format
```
### Session summary — YYYY-MM-DD
**Status:** SUCCESS | PARTIAL | FAILED
**Tasks completed:**
- [TASK-ID] description — verification: <command and output>
**Tasks blocked:**
- [TASK-ID] description — blocked by: <reason>
**Service state:** <one paragraph>
**Anomalies:** <anything unexpected, or NONE>
**Suggested next session P1s:**
- <specific tasks with preconditions>
```

## Architecture invariants — never violate without explicit discussion
1. API port: 8080
2. ntfy port: 8090
3. Data path: ~/paladin-control/data/projects/
4. CPO queue path: ~/dev/queue/
5. Poll interval: 30 seconds
6. Blast radius enforcement: overnight runs LOW/NONE only
7. Backend is single source of truth for frontend data — no direct file reads from JS
8. All project state from ~/projects/*/context/ directories — no separate database
9. Frontend is vanilla JS/HTML/CSS only — no build tools, no npm, no frameworks
10. Services run as systemd user units — not root, not containerized
11. ntfy is the only notification channel — no email, no SMS, no Slack

## Service restart rules
- **NEVER** restart paladin-supervisor.service during task execution.
  To signal config reload: `systemctl --user kill --signal=SIGHUP paladin-supervisor.service`
- paladin-api.service MAY be restarted only as the final step of a task,
  after all code changes are committed, and only when new API endpoints
  need to be activated.

## Blast radius rules
- **LOW/NONE:** proceed autonomously
- **MEDIUM:** write plan to specs/plan-<task>-<date>.md, validate before executing
- **HIGH:** write plan, STOP, write to ~/projects/NOTIFY.md — do not execute

## Prompt Authoring Guidelines

Prompts submitted via the dashboard describe WHAT to implement,
not HOW. When you receive a prompt:

1. Read the relevant files yourself — do not expect inline code
   to be provided. The prompt describes intent and acceptance criteria.

2. Start working immediately — do not read the entire prompt before
   starting. Read one section, implement it, commit, then continue.

3. Commit at each logical checkpoint — not at the end. If you hit
   a problem, earlier checkpoints are preserved.

4. Write blocker.json if you cannot proceed — do not just exit.
   Describe what is blocked and what the fix requires.

5. Print FINISHED WORK as your absolute last action — after all
   commits, after all verification, after writing any summaries.

6. Keep implementations focused — if a prompt asks for 3 things,
   implement them one at a time with a commit after each.

## Known Issues
<!-- Auto-updated by AERS on blocker resolution. Do not remove this section. -->
_No known issues at this time._


## Paladin Orchestration

This project is managed by the Paladin Control Plane (PCP).
Dashboard: https://dashboard.paladinrobotics.com

### Execution conventions
- Print FINISHED WORK as your absolute last action — after all commits
- Commit at each logical checkpoint during a task, not at the end
- Use conventional commit format: type(scope): description [ckpt N]
- Write blocker.json to the active task directory if you cannot proceed
- Read context/AGENTS.md and context/STATUS.md at every session start
- Update context/STATUS.md and context/WORKQUEUE.md before exiting

### Blocker reporting
If blocked, write ~/dev/queue/active/{task_name}/blocker.json:
  type: one of github-auth, api-down, missing-credential, path-issue,
        git-conflict, disk-full, service-crash, network-unreachable,
        missing-dependency, permission-denied, trust-prompt, unknown
  description: one sentence — what failed and why
  fix_instructions: exact steps to resolve
  resumable: true
  checkpoint_commit: last commit hash before blocker, or null
  completed_steps: list of steps already done
  remaining_steps: list of steps still to do
Then print FINISHED WORK and exit cleanly.

### Context schema
paladin-context-system v1.0
Schema reference: ~/projects/paladin-context-system/SCHEMA.md
Patterns library: ~/projects/paladin-context-system/patterns/

### Known Issues
<!-- Auto-updated by AERS on blocker resolution. Do not remove. -->
_No known issues at this time._
