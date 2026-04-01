# WORKQUEUE — Paladin Control Plane
Last updated: 2026-04-01 (session 004)

## Active Sprint
- [ ] PCP-009: Build overnight meta-supervisor — systemd timer, executes overnight-ready P1 tasks, pauses for MEDIUM+ blast radius (requires PCP-006, supervised first run)

## Backlog

### P2
- [ ] PCP-010: Add project archive and restore — archive/restore buttons, collapsed section on home view

## Blocked
- Nothing blocked

## Completed
- [x] 2026-03-30 Bootstrap: CLAUDE.md, context files, subagents, settings.json, WORKQUEUE-MASTER integration
- [x] 2026-03-31 PCP-001: ntfy v2.14.0 on port 8090 — paladin-alerts/sessions/errors topics, Claude Code hooks configured
- [x] 2026-03-31 PCP-002: FastAPI backend on port 8080 — /health, /api/projects, /api/projects/{id}, /api/events SSE, systemd user service, boot persistence
- [x] 2026-03-31 PCP-003: Frontend dashboard — dark theme, project cards, detail views, SSE auto-refresh, mobile-responsive
- [x] 2026-04-01 PCP-004: Chat thread and prompt input — per-project thread.jsonl + prompt-queue.json, GET /thread + POST /prompt, frontend chat UI with bubbles and prompt textarea
- [x] 2026-04-01 PCP-005: Meta-supervisor prompt handler — polls prompt-queue.json every 60s, routes prompts to CPO tasks, systemd service paladin-supervisor
- [x] 2026-04-01 PCP-006: Needs-input handling — POST /needs-input + POST /respond, response file mechanism, ntfy deep link notification, amber badge + response form in dashboard, request_input.py helper for pauseable tasks
- [x] 2026-04-01 PCP-007: Cloudflare Tunnel — cloudflared systemd service, public HTTPS at dashboard.paladinrobotics.com
- [x] 2026-04-01 PCP-008: GitHub OAuth authentication — login page, OAuth flow, session cookies, Tailscale bypass, auth middleware, security hardening (header spoof prevention, open redirect fix, XSS escaping)
