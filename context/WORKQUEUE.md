# WORKQUEUE — Paladin Control Plane
Last updated: 2026-03-30

## Active Sprint
- [ ] PCP-001: Install ntfy notifications — systemd service, test to iPhone via Tailscale, update Claude Code hooks
- [x] PCP-002: Build backend API server (read-only Phase 1) — FastAPI on port 8080, /api/projects, /health, systemd service ✅ 2026-03-31
- [ ] PCP-003: Build frontend dashboard (read-only Phase 1) — home view with project cards, project view with queue/logs, mobile-responsive, SSE

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
- [x] ✅ 2026-03-31 PCP-002: FastAPI backend on port 8080 — /health, /api/projects, /api/projects/{id}, /api/events SSE, systemd user service, boot persistence
