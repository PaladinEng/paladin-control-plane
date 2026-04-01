# STATUS — Paladin Control Plane
Updated: 2026-04-01

## Current State
Phase 3 complete. FastAPI backend on port 8080 with full chat thread API including needs-input/respond flow, frontend dashboard with prompt input and needs-input response UI, ntfy notifications on port 8090 with deep links, meta-supervisor polling prompt queues every 60s. Dashboard prompt-to-CPO pipeline and needs-input pause/resume cycle validated end-to-end. Overnight tasks can now pause and wait for dashboard responses via request_input.py helper.

## Backend API
- **Status:** Running — paladin-api.service active (running)
- **Port:** 8080
- **Endpoints:**
  - /health
  - /api/projects, /api/projects/{id}
  - /api/events (SSE + POST)
  - /api/projects/{id}/thread (GET)
  - /api/projects/{id}/prompt (POST)
  - /api/projects/{id}/needs-input (POST) — task pauses here
  - /api/projects/{id}/respond (POST) — user responds here
- **Service:** systemd user unit, enabled on boot, linger enabled
- **Last verified:** 2026-04-01

## Frontend Dashboard
- **Status:** Live — served from /static/ via FastAPI
- **Views:** Home (project cards grid), Project detail (status, queue, sessions, decisions, chat thread, prompt input, needs-input response)
- **Features:** Dark theme, mobile-responsive, SSE auto-refresh, markdown rendering, chat thread, prompt submission, needs-input amber badge + response form
- **Last verified:** 2026-04-01

## Meta-Supervisor
- **Status:** Running — paladin-supervisor.service active (running)
- **Behavior:** Polls ~/paladin-control/data/projects/*/prompt-queue.json every 60s
- **Routing:** Unhandled prompts → CPO task in ~/dev/queue/pending/
- **Helper:** supervisor/request_input.py — pauseable Claude Code tasks can request input and wait
- **Logs:** logs/supervisor.log
- **Last verified:** 2026-04-01

## ntfy Notifications
- **Status:** Running — ntfy.service active (running)
- **Port:** 8090
- **Version:** 2.14.0
- **Topics:** paladin-alerts, paladin-sessions, paladin-errors
- **Config:** /etc/ntfy/server.yml, base-url http://10.1.10.50:8090
- **Hooks:** Claude Code SessionEnd and SubagentStop post to ntfy via config/ntfy-hooks.sh
- **Deep links:** needs-input notifications link to https://dashboard.paladinrobotics.com/#/project/{id}
- **Last verified:** 2026-04-01

## Cloudflare Tunnel
- **Status:** Not yet configured
- **Preconditions:** PCP-003 complete, manual Cloudflare setup

## GitHub OAuth
- **Status:** Not yet configured
- **Preconditions:** PCP-007 complete, manual GitHub OAuth app creation

## Last Session
Date: 2026-04-01
Done:
- PCP-006: Needs-input handling — POST /needs-input, POST /respond, response file mechanism, ntfy deep link, frontend amber badge + response form, request_input.py helper
- End-to-end test: needs-input → status change → respond → status restored → response file written

## In Progress
- Nothing actively in progress

## Blocked
- Nothing blocked

## Next Session Should Start With
1. PCP-007: Configure Cloudflare Tunnel (requires manual Cloudflare setup)
2. PCP-008: Add GitHub OAuth authentication (requires PCP-007 + manual GitHub OAuth app)
