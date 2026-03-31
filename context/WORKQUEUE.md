# WORKQUEUE — Paladin Control Plane
Last updated: 2026-03-30

## Active Sprint
- (empty — promote from backlog)

## Backlog

### P2
- [ ] PCP-004: Add prompt input and project chat thread — per-project chat, prompt textarea, POST /api/projects/{id}/prompt
- [ ] PCP-005: Build meta-supervisor prompt handler — polls prompt-queue.json, creates CPO tasks, response in thread
- [ ] PCP-006: Add paused/needs-input handling — POST /api/projects/{id}/respond, needs-input badge, ntfy notification
- [ ] PCP-007: Configure Cloudflare Tunnel — cloudflared systemd service, public HTTPS access (requires manual Cloudflare setup)
- [ ] PCP-008: Add GitHub OAuth authentication — public URL requires login, PaladinEng only, Tailscale bypass (requires PCP-007 + manual GitHub OAuth app)
- [ ] PCP-009: Build overnight meta-supervisor — systemd timer, executes overnight-ready P1 tasks, pauses for MEDIUM+ blast radius (requires PCP-006, supervised first run)
- [ ] PCP-010: Add project archive and restore — archive/restore buttons, collapsed section on home view

## Blocked
- Nothing blocked

## Completed
- [x] ✅ 2026-03-30 Bootstrap: CLAUDE.md, context files, subagents, settings.json, WORKQUEUE-MASTER integration
- [x] ✅ 2026-03-31 PCP-001: ntfy v2.14.0 on port 8090 — paladin-alerts/sessions/errors topics, Claude Code hooks configured
- [x] ✅ 2026-03-31 PCP-002: FastAPI backend on port 8080 — /health, /api/projects, /api/projects/{id}, /api/events SSE, systemd user service, boot persistence
- [x] ✅ 2026-03-31 PCP-003: Frontend dashboard — dark theme, project cards, detail views, SSE auto-refresh, mobile-responsive
