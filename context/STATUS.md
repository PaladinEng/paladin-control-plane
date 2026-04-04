# STATUS — Paladin Control Plane
Last verified: 2026-04-04

## Current State
All core systems operational. Backend API on port 8080 serving frontend dashboard with GitHub OAuth for public access via Cloudflare Tunnel. Tailscale (10.1.10.x, 100.x.x.x) and localhost bypass authentication. Meta-supervisor running continuously, polling prompt queues every 30s and auto-executing CPO tasks. Overnight timer scheduled for daily execution at 23:00 UTC. ntfy notification service active on port 8090. Archive and restore endpoints fully functional. Project creation system v1.1 with 4-mode support complete. CPO retry path issues fixed with exponential backoff and max retry limits.

AERS v1.0 implemented (2026-04-04): Autonomous Error Recovery System comprising outcome reconciler, blocker registry, and queue evaluator. New status value `parked` (work paused pending blocker resolution). Patterns library at ~/projects/paladin-context-system/patterns/ with 12 initial blocker types defined. Known Issues sections in project CLAUDE.md files are auto-updated on blocker resolution. No blocking issues.

## Services

| Service | Status | Type | Verified |
|---------|--------|------|----------|
| paladin-api.service | active (running) | systemd user | 2026-04-02 |
| paladin-supervisor.service | active (running) | systemd user | 2026-04-02 |
| ntfy.service | active (running) | systemd system | 2026-04-02 |
| cloudflared | active (running) | systemd system | 2026-04-02 |
| paladin-overnight.timer | active | systemd user | 2026-04-02 |

## Backend API

**Status:** Running — paladin-api.service active
**Port:** 8080 (listens on 0.0.0.0)
**Python:** 3.12+ in venv at ~/.venv/

**Verified Endpoints:**
- `GET /health` — returns `{"status":"ok","version":"0.1.0"}`
- `GET /auth/status` — returns authenticated:true (Tailscale bypass works)
- `GET /auth/login`, `/auth/callback`, `/auth/logout`
- `GET /api/projects` — returns 2 projects: homelab-infra, paladin-control-plane
- `GET /api/projects/{id}` — returns single project detail
- `GET /api/events` (SSE) — server-sent events stream
- `POST /api/events` — post event to SSE stream
- `GET /api/projects/{id}/thread` — returns thread entries (26 entries verified for PCP)
- `POST /api/projects/{id}/prompt` — submit prompt to project
- `POST /api/projects/{id}/needs-input` — create needs-input thread entry
- `POST /api/projects/{id}/respond` — create response thread entry
- `POST /api/projects/{id}/prompts/batch` — submit multiple prompts at once (JSON body)
- `POST /api/projects/{id}/prompts/upload` — upload .md/.txt file, auto-parse into queued prompts
- `POST /api/projects/{id}/archive` — archives project, returns `{"status":"archived"}`
- `POST /api/projects/{id}/restore` — restores project, returns `{"status":"active"}`
- `POST /api/projects/create` — 4-mode project creation (existing-repo, new-repo, imported-repo, prompted-start)
- `POST /api/projects/{id}/provisioning-complete` — mark project provisioning status
- `POST /api/projects/uploads` — brief file upload endpoint
- `GET /api/system/config` — system configuration endpoint

**Authentication:** GitHub OAuth for public URLs (client ID in systemd env), Tailscale/localhost bypass via TAILSCALE_PREFIXES in auth_service.py

**Systemd:** systemd user unit, enabled on boot, loginctl enable-linger applied

**Last verified:** 2026-04-02

## Frontend Dashboard

**Status:** Live and operational
**Location:** Served from `/static/` via FastAPI
**Files:** index.html, js/app.js, js/api.js, js/sse.js, js/views/home.js, js/views/project.js

**Features:**
- Home view: cluster health cards, project status grid
- Project view: queue panel, session log viewer, chat thread, prompt input, needs-input response
- Project creation modal: 4-mode selection (existing-repo, new-repo, imported-repo, prompted-start)
- Provisioning status badge with .paladin-config.yaml support
- Dark theme, mobile-responsive (iPhone Safari tested)
- SSE-driven live updates
- Archive/restore functions verified in api.js

**Last verified:** 2026-04-02

## GitHub OAuth

**Status:** Active — PaladinEng account only
**Client ID:** Loaded in systemd drop-in (paladin-api.service.d/oauth.conf)
**AuthMiddleware:** Registered in main.py
**Flow:** Public URL → login page → GitHub OAuth → signed session cookie (7-day lifetime)

**Bypass Rules:**
- Tailscale IPs: 10.1.10.x, 100.x.x.x (direct access, no auth required)
- localhost: 127.0.0.1 (local testing, no auth required)

**Callback URL:** https://dashboard.paladinrobotics.com/auth/callback

**Last verified:** 2026-04-02

## Meta-Supervisor

**Status:** Running — paladin-supervisor.service active
**Location:** systemd user service with npm-global in PATH
**Poll Frequency:** Every 60 seconds

**Behavior:**
- Monitors ~/paladin-control/data/projects/*/prompt-queue.json
- Creates CPO tasks in ~/dev/queue/pending/
- Auto-executes via queue-worker-full-pass.sh
- Timeout: 30 minutes per task
- Task.md: Full objective from prompt content, acceptance criteria require actual execution
- Hang detector checks git commits before retry — if work was committed, marks prompt handled instead of retrying
- Prompts marked handled before execution to prevent duplicate retry on supervisor restart
- Hang detector threshold: 10 minutes (timeout wrapper handles 30min hard cap)
- Task.md templates include explicit exit instruction to prevent Claude Code hang-on-exit
- queue-run-codex.sh wraps claude with `timeout 1800` and detects FINISHED WORK signal
- CPO retry path: exponential backoff (0/60/120/300/600 seconds), max 5 attempts, manual-only warning in generated run-claude.sh
- Verified queue-run-codex.sh does not call run-claude.sh

**Helper Tools:**
- supervisor/request_input.py — pauseable Claude Code tasks can request input and wait
- Data directories exist for homelab-infra and paladin-control-plane

**Logs:** logs/supervisor.log
**Recent Activity:** Created task for 2026-04-02 smoke test session, CPO retry path fixes applied 2026-04-02

**Last verified:** 2026-04-02

## Overnight Timer

**Status:** Active — paladin-overnight.timer enabled, next trigger 2026-04-02 23:00 UTC
**Schedule:** Daily at 23:00 UTC
**Script:** supervisor/overnight.py
**Execution:** Runs 0 overnight-ready tasks currently (expected state)

**Behavior:**
- Reads ~/projects/WORKQUEUE-MASTER.md P1 section
- Executes overnight-ready tasks with blast-radius LOW/NONE
- Skips MEDIUM/HIGH blast-radius tasks with ntfy notification + NOTIFY.md entry

**Validation:** overnight.py syntax valid, parser working

**Logs:** logs/overnight.log

**Last verified:** 2026-04-02

## ntfy Notifications

**Status:** Running — ntfy.service active (systemd system service)
**Port:** 8090
**Version:** 2.14.0

**Topics:**
- paladin-alerts — general alerts
- paladin-sessions — session events
- paladin-errors — error notifications

**Features:**
- Test notification verified successful 2026-04-02
- Deep links: needs-input notifications link to https://dashboard.paladinrobotics.com/#/project/{id}

**Last verified:** 2026-04-02

## Cloudflare Tunnel

**Status:** Active — cloudflared running (systemd SYSTEM service, not user service)
**Service Type:** System service (started 2026-04-01, running continuously)
**Public URL:** https://dashboard.paladinrobotics.com → localhost:8080
**HTTP Status:** 200 OK on public URL

**Authentication:** GitHub OAuth required for public access, Tailscale bypass for internal access

**Note:** Runs as system service (not user service as initially documented). Functionally correct, architecture decision made in earlier session.

**Last verified:** 2026-04-02

## Data Paths

| Path | Purpose |
|------|---------|
| ~/projects/*/context/ | Project state (WORKQUEUE.md, STATUS.md, DECISIONS.md, AGENTS.md) |
| ~/paladin-control/data/projects/*/ | Thread data and prompt queues |
| ~/dev/queue/{pending,active,completed,failed}/ | CPO task queue |
| ~/dev/projects/codex-project-orchestrator/scripts/ | Queue runner scripts (queue-run-codex.sh, queue-worker-full-pass.sh) |
| ~/projects/paladin-control-plane/logs/ | Supervisor and overnight logs |
| ~/.venv/ | Python 3.12+ virtual environment |

## AERS (Autonomous Error Recovery System)

**Status:** v1.0 implemented
**Components:**
- Outcome reconciler — classifies task outcomes and triggers recovery flows
- Blocker registry — tracks 12 initial blocker types, auto-creates new types on first occurrence
- Queue evaluator — skips parked prompts, continues other projects' work

**Patterns library:** ~/projects/paladin-context-system/patterns/
**New status values:** `parked` (work paused pending blocker resolution)
**CLAUDE.md integration:** Known Issues section auto-updated on blocker resolution

## In Progress

None. All systems operational.

## Blocked

None. All dependencies satisfied.

## Known Issues

1. **cloudflared service type:** Runs as systemd SYSTEM service, not user service (differs from initial documentation but functions correctly)
2. **Queue runner path:** queue-run-codex.sh is in ~/dev/projects/codex-project-orchestrator/scripts/ not ~/dev/scripts/ (documented for reference)

## Session History

- Sessions 001-005 completed (2026-03-30 through 2026-04-01)
- PCP-001 through PCP-015 completed
- PCP-011 (PATH fix for Claude CLI in systemd services) merged 2026-04-01
- Smoke test verification 2026-04-02: all systems operational
- PCP-013 (batch prompt upload) completed 2026-04-02
- PCP-014 (spawn new projects) completed 2026-04-02
- PCP-015 (WORKQUEUE web editor) completed 2026-04-02
- PCP-017 (project creation system v1.1) completed 2026-04-02
- Session 2026-04-02: Fixed CPO retry path issues — exponential backoff, max retry limit, manual-only warning
- Overnight 2026-04-02: PCP-016 — SSE broadcast code duplication fixed, broadcast_project_update() helper extracted
- Overnight 2026-04-02: PCP-017b — Respond endpoint double-tap race fixed, atomic check-and-set in submit_response
- Overnight 2026-04-02: PCP-018 — Hardcoded DATA_ROOT paths consolidated into backend/config.py, all files import from single source
- 2026-04-04: AERS v1.0 (AERS-001 through AERS-012) — outcome reconciler, blocker registry, queue evaluator, checkpoint/resume, pattern recording, end-to-end tests, Known Issues auto-update

## Last Updated

Date: 2026-04-04
Verification Method: AERS-012 context file updates — all AERS items completed and documented
