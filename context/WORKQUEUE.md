# WORKQUEUE — Paladin Control Plane
Last updated: 2026-04-02T00:15Z

## Active Sprint

### [PCP-011] Unify ntfy and dashboard thread notifications
project: paladin-control-plane
parallel: YES
blast-radius: NONE
overnight-ready: YES
preconditions: PCP-009 complete
done-when:
  - Every ntfy notification also appears as a thread event entry
  - Every thread event also triggers an ntfy push notification
  - Single code path in poll_prompts.py handles both channels together

## P3 Backlog

### [PCP-012] Session log download from dashboard
project: paladin-control-plane
parallel: YES
blast-radius: NONE
overnight-ready: YES
preconditions: PCP-003 complete
done-when:
  - Session log filenames in project view are clickable download links
  - GET /api/projects/{id}/logs/{filename} serves the raw log file
  - Works on mobile (iOS Safari download)

### [PCP-013] Batch prompt upload
project: paladin-control-plane
parallel: YES
blast-radius: NONE
overnight-ready: YES
preconditions: PCP-004 complete
done-when:
  - File upload or multi-line paste mode in project view
  - Each line or section becomes a separate queued prompt
  - Prompts queued in order and executed sequentially
  - Upload confirmation shows how many prompts were queued

### [PCP-014] WORKQUEUE web editor
project: paladin-control-plane
parallel: YES
blast-radius: NONE
overnight-ready: YES
preconditions: PCP-003 complete
done-when:
  - Form in project view to add/edit/reprioritize WORKQUEUE items
  - Writes directly to project context/WORKQUEUE.md
  - Changes reflected in dashboard on next refresh

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
- [x] 2026-04-01 PCP-010: Add project archive and restore ✅ — archive/restore buttons, collapsed section on home view
- [x] 2026-04-02 PCP-011: Morning briefing ✅ superseded — functionality covered by PCP-009 overnight timer and ntfy notifications
