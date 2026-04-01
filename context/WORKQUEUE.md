# WORKQUEUE — Paladin Control Plane
Last updated: 2026-04-01 (session 005)

## Active Sprint
- [ ] PCP-010: Add project archive and restore — archive/restore buttons, collapsed section on home view

## Backlog

(empty)

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
- [x] 2026-04-01 PCP-009: Overnight meta-supervisor — fixed task.md generation (full objectives, not just acknowledgement), auto-execution via queue-worker-full-pass.sh, overnight.py + systemd timer at 23:00, blast radius enforcement (LOW/NONE only)
- [x] 2026-04-01 PCP-011: Fix claude CLI PATH — systemd override adds ~/.npm-global/bin to PATH, queue-run-codex.sh uses CLAUDE_BIN fallback, end-to-end test passed
