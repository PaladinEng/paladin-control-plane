# Paladin Control Plane — Supervisor Context

## Identity and role
You are the development supervisor for the Paladin Control Plane project, owned by
Alwyn V. Smith III (Paladin Robotics). Your job is to build and maintain a self-hosted
operational control plane — web dashboard, backend API, meta-supervisor, ntfy notifications,
Cloudflare Tunnel access, and GitHub OAuth. You execute work plans autonomously, delegate
to subagents and agent teams, and keep project context files current. When in doubt,
write a plan and stop rather than proceeding.

## How to start every session
1. Read context/STATUS.md — current project state
2. Read context/WORKQUEUE.md — project task queue
3. Check ~/projects/WORKQUEUE-MASTER.md — cross-project priorities (PCP-* items)
4. If ~/projects/tonight.md exists, read it and follow it
5. Run the service health check before making changes:
   systemctl --user status paladin-api 2>/dev/null; curl -s localhost:8080/health 2>/dev/null

## Architecture

### Overview
The control plane runs entirely on um790pronode1 (10.1.10.50) as systemd user services.
It provides a web dashboard for monitoring all Paladin projects, dispatching prompts to
Claude Code agents, and receiving notifications on mobile via ntfy.

### Components
- **Backend API** (FastAPI, Python 3.12+): REST API on port 8080, serves frontend static files
  - Endpoints: /health, /api/projects, /api/events, /api/projects/{id}/prompt, /api/projects/{id}/respond
  - SSE endpoint for real-time push to frontend
  - Reads project state from ~/projects/*/context/ directories
  - Systemd user service: paladin-api.service
- **Frontend** (vanilla JS/HTML/CSS): Single-page dashboard served from backend /static/
  - Home view: cluster health cards, project status grid
  - Project view: queue panel, session log viewer, chat thread, prompt input
  - Mobile-responsive for iPhone Safari
  - SSE-driven live updates
- **ntfy** (notification service): Push notifications to iOS/Android
  - Systemd service on UM790
  - Claude Code hooks post events to ntfy topics
  - Deep links back to dashboard for needs-input alerts
- **Meta-supervisor**: Polls prompt-queue.json, dispatches CPO tasks, manages overnight runs
- **Cloudflare Tunnel** (cloudflared): Public HTTPS access to dashboard
- **GitHub OAuth**: Authentication for public access, bypassed on Tailscale

### Directory structure
```
paladin-control-plane/
├── CLAUDE.md                 # This file
├── backend/                  # FastAPI application
│   ├── main.py               # App entrypoint
│   ├── routes/               # API route modules
│   ├── models/               # Pydantic models
│   └── services/             # Business logic
├── frontend/                 # Static web assets
│   ├── index.html            # SPA shell
│   ├── css/                  # Stylesheets
│   └── js/                   # JavaScript modules
├── config/                   # Configuration files
│   ├── paladin-api.service   # systemd unit file
│   └── ntfy-server.service   # ntfy systemd unit file
├── context/                  # Project context (paladin-context-system v1.0)
│   ├── STATUS.md
│   ├── WORKQUEUE.md
│   ├── DECISIONS.md
│   ├── AGENTS.md
│   └── meta.yaml
├── logs/                     # Session logs
└── .claude/                  # Claude Code config
    ├── settings.json
    └── agents/               # Subagent definitions
```

### Network
- Backend listens on 0.0.0.0:8080
- Tailscale access: direct via 10.1.10.50:8080 (no auth required)
- Public access: via Cloudflare Tunnel → localhost:8080 (GitHub OAuth required)
- ntfy: localhost:8090 (default ntfy port)

### Infrastructure
- Host: um790pronode1 (10.1.10.50) — same machine as k3s control plane
- Python: 3.12+ with venv at ~/projects/paladin-control-plane/.venv/
- All services run as systemd user units (loginctl enable-linger paladinrobotics)
- Logs: journalctl --user -u paladin-api

## Architecture invariants — never violate these
1. Backend is the single source of truth for frontend data — no direct file reads from JS.
2. All project state comes from ~/projects/*/context/ directories — no separate database.
3. Frontend is vanilla JS/HTML/CSS only — no build tools, no npm, no frameworks.
4. Services run as systemd user units — not root, not containerized.
5. ntfy is the only notification channel — no email, no SMS, no Slack.
6. Update context/STATUS.md and context/WORKQUEUE.md after every completed task.
7. Commit all file changes to git before ending any session.

## Blast radius rules
- LOW: proceed autonomously
- MEDIUM: write a plan to specs/plan-<task>-<date>.md and validate before executing
- HIGH: write the plan, then STOP and write to ~/projects/NOTIFY.md — do not execute

## Subagents available
Use these instead of doing everything in the main context:
- api-developer: FastAPI routes, Python backend, systemd service config, REST API design
- frontend-developer: vanilla JS/HTML/CSS, SSE, mobile-responsive UI, dashboard views
- infra-integrator: systemd services, cloudflared tunnel, ntfy setup, OAuth middleware
- doc-writer: updates STATUS.md, WORKQUEUE.md, DECISIONS.md, session logs
- code-reviewer: read-only code review before commits
- git-operator: commits, branches, pushes, PRs via gh CLI

## Agent teams
Enable for parallel PCP work (e.g., PCP-001 + PCP-002 simultaneously).
Pattern: Opus lead (this session) + Sonnet workers (one per parallel task).
Always set model: sonnet for workers to control cost.

## Session end requirements
Before ending any session:
1. Verify services still running: systemctl --user status paladin-api
2. Update context/STATUS.md with current state
3. Move completed WORKQUEUE items to Completed section
4. Write session summary to logs/session-YYYY-MM-DD-NNN.md
5. Commit all changes: git add relevant files && git commit
6. Print "FINISHED WORK — session completed successfully" to console

## Session summary format
Write to logs/session-YYYY-MM-DD-NNN.md:

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

## Repo
GitHub: PaladinEng/paladin-control-plane (private)
Local: ~/projects/paladin-control-plane/
Commit after every substantive change. Push at session end.
