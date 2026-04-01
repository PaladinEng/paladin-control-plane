# STATUS — Paladin Control Plane
Updated: 2026-04-01

## Current State
Phase 4 complete. FastAPI backend on port 8080 with GitHub OAuth authentication for public access via Cloudflare Tunnel. Tailscale and localhost access bypass auth. Chat thread API with needs-input/respond flow, frontend dashboard with prompt input UI, ntfy notifications on port 8090 with deep links, meta-supervisor polling prompt queues every 60s. All services operational.

## Backend API
- **Status:** Running — paladin-api.service active (running)
- **Port:** 8080
- **Endpoints:**
  - /health
  - /auth/login, /auth/callback, /auth/logout, /auth/status
  - /api/projects, /api/projects/{id}
  - /api/events (SSE + POST)
  - /api/projects/{id}/thread (GET)
  - /api/projects/{id}/prompt (POST)
  - /api/projects/{id}/needs-input (POST)
  - /api/projects/{id}/respond (POST)
- **Auth:** GitHub OAuth for public URLs, Tailscale/localhost bypass
- **Service:** systemd user unit, enabled on boot, linger enabled
- **Last verified:** 2026-04-01

## Frontend Dashboard
- **Status:** Live — served from /static/ via FastAPI
- **Views:** Home (project cards grid, auth indicator), Project detail (status, queue, sessions, decisions, chat thread, prompt input, needs-input response)
- **Features:** Dark theme, mobile-responsive, SSE auto-refresh, markdown rendering, chat thread, prompt submission, needs-input handling, auth status display
- **Last verified:** 2026-04-01

## GitHub OAuth
- **Status:** Active — PaladinEng account only
- **Flow:** Public URL → login page → GitHub OAuth → signed session cookie (7 day lifetime)
- **Bypass:** Tailscale IPs (10.1.10.x, 100.x.x.x) and localhost (127.0.0.1) bypass auth
- **Credentials:** systemd drop-in at paladin-api.service.d/oauth.conf
- **Callback URL:** https://dashboard.paladinrobotics.com/auth/callback
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
- **Deep links:** needs-input notifications link to https://dashboard.paladinrobotics.com/#/project/{id}
- **Last verified:** 2026-04-01

## Cloudflare Tunnel
- **Status:** Active — cloudflared running
- **URL:** https://dashboard.paladinrobotics.com → localhost:8080
- **Auth:** GitHub OAuth required (Tailscale bypass for internal access)

## Last Session
Date: 2026-04-01
Done:
- PCP-008: GitHub OAuth authentication — login page, OAuth flow, session cookies, Tailscale bypass, auth middleware, frontend auth indicator
- Fixed: localhost (127.0.0.1) added to trusted IPs for supervisor/service-to-service calls
- Deps: httpx and itsdangerous installed in venv

## In Progress
- Nothing actively in progress

## Blocked
- Nothing blocked

## Next Session Should Start With
1. PCP-009: Build overnight meta-supervisor (requires supervised daytime first run)
2. PCP-010: Add project archive and restore
